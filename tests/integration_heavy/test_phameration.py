"""
Unit tests for functions in phameration.py
"""

import os
import shutil
import unittest
import subprocess
import sys
from pathlib import Path

import pymysql
import sqlalchemy

from pdm_utils.functions.phameration import *
from pdm_utils.functions import mysqldb


# Import helper functions to build mock database
unittest_file = Path(__file__)
test_dir = unittest_file.parent.parent
if str(test_dir) not in set(sys.path):
    sys.path.append(str(test_dir))
import test_db_utils

# Standard pdm_anon user/pwd and test_db
engine_string = test_db_utils.create_engine_string()


class TestPhamerationFunctions(unittest.TestCase):
    def setUp(self):
        self.engine = sqlalchemy.create_engine(engine_string, echo=False)
        self.temp_dir = "/tmp/pdm_utils_tests_phamerate"
        # Create test database that contains data for several phages.
        test_db_utils.create_filled_test_db()


    def tearDown(self):
        self.engine.dispose()
        test_db_utils.remove_db()

        run_dir = Path.cwd()
        err_file = run_dir.joinpath("error.log")
        if err_file.exists():
            print("Found leftover blastclust file... removing")
            err_file.unlink()

    def test_1_get_pham_geneids(self):
        """Verify we get back a dictionary"""
        old_phams = get_pham_geneids(self.engine)
        # old_phams should be a dict
        self.assertEqual(type(old_phams), type(dict()))

    def test_2_get_pham_colors(self):
        """Verify we get back a dictionary"""
        old_colors = get_pham_colors(self.engine)
        # old_colors should be a dict
        self.assertEqual(type(old_colors), type(dict()))

    def test_3_get_pham_geneids_and_colors(self):
        """Verify both dictionaries have the same keys"""
        old_phams = get_pham_geneids(self.engine)
        old_colors = get_pham_colors(self.engine)

        # Can't have same keys without the same number of keys...
        with self.subTest():
            self.assertEqual(len(old_phams), len(old_colors))

        # Intersection should be equal to either set of keys - check against old_phams
        with self.subTest():
            self.assertEqual(set(old_phams.keys()).intersection(set(old_colors.keys())), set(old_phams.keys()))

    def test_4_get_unphamerated_genes(self):
        """Verify we get back a set of length 0"""
        unphamerated = get_new_geneids(self.engine)
        # unphamerated should be a set
        with self.subTest():
            self.assertEqual(type(unphamerated), type(set()))
        # test_db has 0 unphamerated genes
        with self.subTest():
            self.assertEqual(len(unphamerated), 0)

    def test_5_map_geneids_to_translations(self):
        """Verify we get back a dictionary"""
        gs_to_ts = map_geneids_to_translations(self.engine)

        command = "SELECT distinct(GeneID) FROM gene"
        results = mysqldb.query_dict_list(self.engine, command)

        # gs_to_ts should be a dictionary
        with self.subTest():
            self.assertEqual(type(gs_to_ts), type(dict()))
        # gs_to_ts should have the right number of geneids
        with self.subTest():
            self.assertEqual(len(gs_to_ts), len(results))

    def test_6_map_translations_to_geneids(self):
        """Verify we get back a dictionary"""
        ts_to_gs = map_translations_to_geneids(self.engine)

        command = "SELECT distinct(Translation) FROM gene"
        results = mysqldb.query_dict_list(self.engine, command)


        # ts_to_gs should be a dictionary
        with self.subTest():
            self.assertEqual(type(ts_to_gs), type(dict()))
        # ts_to_gs should have the right number of translations
        with self.subTest():
            self.assertEqual(len(ts_to_gs), len(results))

    def test_7_refresh_tempdir_1(self):
        """Verify if no temp_dir, refresh can make one"""
        if not os.path.exists(self.temp_dir):
            refresh_tempdir(self.temp_dir)
        self.assertTrue(os.path.exists(self.temp_dir))

    def test_8_refresh_tempdir_2(self):
        """Verify if temp_dir with something, refresh makes new empty one"""
        filename = f"{self.temp_dir}/test.txt"
        if not os.path.exists(self.temp_dir):
            refresh_tempdir(self.temp_dir)
        f = open(filename, "w")
        f.write("test\n")
        f.close()

        # Our test file should now exist
        with self.subTest():
            self.assertTrue(os.path.exists(filename))

        # Refresh temp_dir
        refresh_tempdir(self.temp_dir)

        # temp_dir should now exist, but test file should not
        with self.subTest():
            self.assertTrue(os.path.exists(self.temp_dir))
        with self.subTest():
            self.assertFalse(os.path.exists(filename))

    def test_9_write_fasta(self):
        """Verify file gets written properly"""
        filename = f"{self.temp_dir}/input.fasta"

        # refresh_tempdir
        refresh_tempdir(self.temp_dir)

        # Get translations to geneid mappings
        ts_to_gs = map_translations_to_geneids(self.engine)

        # Write fasta
        write_fasta(ts_to_gs, self.temp_dir)

        # Read fasta, make sure number of lines is 2x number of unique translations
        with open(filename, "r") as fh:
            lines = fh.readlines()

        with self.subTest():
            self.assertEqual(len(lines), 2 * len(ts_to_gs))

        # all odd-index lines should map to a key in ts_to_gs
        for i in range(len(lines)):
            if i % 2 == 1:
                with self.subTest():
                    self.assertTrue(lines[i].lstrip(">").rstrip() in ts_to_gs.keys())

    # TODO: comment out this method if you don't have blast_2.2.14 binaries
    def test_10_create_blastdb(self):
        """Verify blastclust database gets made"""
        refresh_tempdir(self.temp_dir)
        db_file = f"{self.temp_dir}/sequenceDB"

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("blast", self.temp_dir)

        # Check that database files were made
        for ext in ["phr", "pin", "psd", "psi", "psq"]:
            with self.subTest():
                self.assertTrue(os.path.exists(f"{db_file}.{ext}"))

    def test_11_create_mmseqsdb(self):
        """Verify mmseqs database gets made"""
        refresh_tempdir(self.temp_dir)
        db_file = f"{self.temp_dir}/sequenceDB"

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("mmseqs", self.temp_dir)

        # Check that database file was made
        self.assertTrue(os.path.exists(db_file))

    def test_12_create_clusterdb(self):
        """Verify no database file gets made"""
        refresh_tempdir(self.temp_dir)
        db_file = f"{self.temp_dir}/sequenceDB"

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("unknown", self.temp_dir)

        # Check that database file was not made
        self.assertFalse(os.path.exists(db_file))

    # TODO: comment out this method if you don't have blast_2.2.14 binaries
    def test_13_phamerate_blast(self):
        """Verify we can phamerate with blastclust"""
        refresh_tempdir(self.temp_dir)

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("blast", self.temp_dir)

        phamerate(get_program_params("blast"), "blast", self.temp_dir)

        # Make sure clustering output file exists
        self.assertTrue(os.path.exists(f"{self.temp_dir}/output.txt"))

    def test_14_phamerate_mmseqs(self):
        """Verify we can phamerate with mmseqs2"""
        refresh_tempdir(self.temp_dir)

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("mmseqs", self.temp_dir)

        phamerate(get_program_params("mmseqs"), "mmseqs", self.temp_dir)

        # Make sure clustering output file exists
        self.assertTrue(os.path.exists(f"{self.temp_dir}/clusterDB.index"))

    def test_15_phamerate_unknown(self):
        """Verify we cannot phamerate with unknown"""
        refresh_tempdir(self.temp_dir)

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("unknown", self.temp_dir)

        phamerate(get_program_params("unknown"), "unknown", self.temp_dir)

        # Make sure clustering output file does not exist
        self.assertFalse(os.path.exists(f"{self.temp_dir}/clusterDB"))

    # TODO: comment out this method if you don't have blast_2.2.14 binaries
    def test_16_parse_blast_output(self):
        """Verify we can open and parse blastclust output"""
        refresh_tempdir(self.temp_dir)

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("blast", self.temp_dir)

        phamerate(get_program_params("blast"), "blast", self.temp_dir)

        phams = parse_output("blast", self.temp_dir)

        # The number of phams should be greater than 0 and less than or equal to
        # the number of distinct translations
        with self.subTest():
            self.assertEqual(type(phams), type(dict()))
        with self.subTest():
            self.assertGreater(len(phams), 0)
        with self.subTest():
            self.assertLessEqual(len(phams), len(ts_to_gs))

    def test_17_parse_mmseqs_output(self):
        """Verify we can open and parse MMseqs2 output"""
        refresh_tempdir(self.temp_dir)

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("mmseqs", self.temp_dir)

        phamerate(get_program_params("mmseqs"), "mmseqs", self.temp_dir)

        phams = parse_output("mmseqs", self.temp_dir)

        # The number of phams should be greater than 0 and less than or equal to
        # the number of distinct translations
        with self.subTest():
            self.assertEqual(type(phams), type(dict()))
        with self.subTest():
            self.assertGreater(len(phams), 0)
        with self.subTest():
            self.assertLessEqual(len(phams), len(ts_to_gs))

    def test_18_parse_unknown_output(self):
        """Verify we cannot open and parse unknown output"""
        refresh_tempdir(self.temp_dir)

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("unknown", self.temp_dir)

        phamerate(get_program_params("unknown"), "unknown", self.temp_dir)

        phams = parse_output("unknown", self.temp_dir)

        # The number of phams should be greater than 0 and less than or equal to
        # the number of distinct translations
        with self.subTest():
            self.assertEqual(type(phams), type(dict()))
        with self.subTest():
            self.assertEqual(len(phams), 0)

    def test_19_reintroduce_duplicates(self):
        """Verify that we can put de-duplicated GeneIDs back together"""
        refresh_tempdir(self.temp_dir)
        gs_to_ts = map_geneids_to_translations(self.engine)

        ts_to_gs = map_translations_to_geneids(self.engine)
        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("mmseqs", self.temp_dir)
        phamerate(get_program_params("mmseqs"), "mmseqs", self.temp_dir)

        new_phams = parse_output("mmseqs", self.temp_dir)

        re_duped_phams = reintroduce_duplicates(new_phams=new_phams,
                                                trans_groups=ts_to_gs,
                                                genes_and_trans=gs_to_ts)

        geneid_total = 0
        for key in re_duped_phams.keys():
            geneid_total += len(re_duped_phams[key])

        # All geneids should be represented in the re_duped_phams
        self.assertEqual(geneid_total, len(gs_to_ts.keys()))

    def test_20_preserve_phams(self):
        """Verify that pham preservation seems to be working"""
        refresh_tempdir(self.temp_dir)

        old_phams = get_pham_geneids(self.engine)
        old_colors = get_pham_colors(self.engine)
        unphamerated = get_new_geneids(self.engine)

        gs_to_ts = map_geneids_to_translations(self.engine)
        ts_to_gs = map_translations_to_geneids(self.engine)

        write_fasta(ts_to_gs, self.temp_dir)

        create_clusterdb("mmseqs", self.temp_dir)

        phamerate(get_program_params("mmseqs"), "mmseqs", self.temp_dir)

        new_phams = parse_output("mmseqs", self.temp_dir)

        new_phams = reintroduce_duplicates(new_phams=new_phams,
                                           trans_groups=ts_to_gs,
                                           genes_and_trans=gs_to_ts)

        final_phams, new_colors = preserve_phams(old_phams=old_phams,
                                                 new_phams=new_phams,
                                                 old_colors=old_colors,
                                                 new_genes=unphamerated)

        # Final phams should be a dict with same number of keys as new_phams
        # since we aren't re-dimensioning, just renaming some keys
        with self.subTest():
            self.assertEqual(type(final_phams), type(dict()))
        with self.subTest():
            self.assertEqual(len(final_phams), len(new_phams))

        # New colors should be a dict with the same number of keys as
        # final_phams
        with self.subTest():
            self.assertEqual(type(new_colors), type(dict()))
        with self.subTest():
            self.assertEqual(len(new_colors), len(final_phams))

        # Can't compare the keys or phams since there's no guarantee that
        # any of the phams were preserved but we can make sure all genes are
        # accounted for
        genes_1_count = len(unphamerated)
        for key in old_phams.keys():
            genes_1_count += len(old_phams[key])
        genes_2_count = 0
        for key in new_phams.keys():
            genes_2_count += len(new_phams[key])
        with self.subTest():
            self.assertEqual(genes_1_count, genes_2_count)

    # Don't really have a good way to verify that reinsert_pham_data() or
    # fix_miscolored_phams() appear to be working properly, but both functions
    # have undergone rigorous manual checks to make sure the MySQL commands
    # and python code work together to come to the correct output


def refresh_tempdir(tmpdir):
    """
    Recursively deletes tmpdir if it exists, otherwise makes it
    :param tmpdir: directory to refresh
    :return:
    """
    if os.path.exists(tmpdir):
        shutil.rmtree(tmpdir)
    os.makedirs(tmpdir)


def get_program_params(program):
    """
    Argparse-free version of same-named function in phameration.py -
    uses hard-coded default values that are the same for all params
    that overlap between the two supported programs
    :param program: clustering program in ["blast", "mmseqs"]
    :return: params dictionary
    """
    if program == "blast":
        params = {"-S": 40,
                  "-L": float(80)/100,
                  "-a": 4}
    elif program == "mmseqs":
        params = {"--threads": 4,
                  "-v": 3,
                  "--cluster-steps": 2,
                  "--max-seqs": 500,
                  "--min-seq-id": float(40)/100,
                  "-c": float(80)/100,
                  "--alignment-mode": 3,
                  "--cov-mode": 0,
                  "--cluster-mode": 0}
    else:
        print(f"Unrecognized program {program}")
        return dict()

    return params


if __name__ == '__main__':
    unittest.main()
