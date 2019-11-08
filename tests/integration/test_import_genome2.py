"""Integration tests for the entire import pipeline."""

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.Alphabet import IUPAC
from Bio.SeqRecord import SeqRecord
from Bio.SeqFeature import SeqFeature, FeatureLocation, CompoundLocation
from Bio.SeqFeature import ExactPosition, BeforePosition, Reference
from collections import OrderedDict
from datetime import datetime, date
import csv
import logging
from pathlib import Path
import pymysql
import shutil
import subprocess
import unittest
from unittest.mock import patch
from pdm_utils import run
from pdm_utils.classes import mysqlconnectionhandler as mch



# Set up a log file to catch all logging for review.
# Note: this should overwrite logging output file in import_genome pipeline.
import_pipeline_test_log = Path("~/testing_log.txt")
import_pipeline_test_log = import_pipeline_test_log.expanduser()
import_pipeline_test_log = import_pipeline_test_log.resolve()
logging.basicConfig(filename=import_pipeline_test_log, filemode="w",
                    level=logging.DEBUG)

# Format of the date the script imports into the database.
current_date = datetime.today().replace(hour=0, minute=0,
                                        second=0, microsecond=0)

# How the output folder is named.
results_folder_date = date.today().strftime("%Y%m%d")
results_folder = Path(f"{results_folder_date}_results")
default_output_path = Path("/tmp/", results_folder)

pipeline = "import_dev"



# The following integration tests user the 'pdm_anon' MySQL user.
# It is expected that this user has all privileges for 'test_db' database.
user = "pdm_anon"
pwd = "pdm_anon"
db = "test_db"
unittest_file = Path(__file__)
unittest_dir = unittest_file.parent
schema_file = "test_schema5.sql"
schema_filepath = Path(unittest_dir, "test_files/", schema_file)

# The primary genome used for the following integration tests is
# Alice ("test_flat_file_10.gb"),
# Alice is a large genome with:
# 1. a gene that wraps around the genome termini.
# 2. a tail assembly chaperone gene that is a compound feature.
# 3. tRNA and tmRNA genes.
base_flat_file = Path("test_flat_file_10.gb")
base_flat_file_path = Path(unittest_dir, "test_files/", base_flat_file)


# Set up paths for all primary input and output folders.
base_dir = Path(unittest_dir, "test_wd/test_import")
import_table_name = Path("import_table.csv")
import_table = Path(base_dir, import_table_name)
genome_folder = Path(base_dir, "genome_folder")
output_folder = Path(base_dir, "output_folder")
log_file_name = Path("import_log.txt")
log_file = Path(output_folder, log_file_name)
alice_flat_file = Path("temp_alice.gb")
alice_flat_file_path = Path(genome_folder, "temp_alice.gb")
results_path = Path(output_folder, results_folder)
success_path = Path(results_path, "success")
success_table_path = Path(success_path, "import_tickets.csv")
success_genomes_path = Path(success_path, "genomes")
success_alice_path = Path(success_genomes_path, alice_flat_file)
fail_path = Path(results_path, "fail")
fail_table_path = Path(fail_path, "import_tickets.csv")
fail_genomes_path = Path(fail_path, "genomes")
fail_alice_path = Path(fail_genomes_path, alice_flat_file)







def create_new_db(schema_file, db, user, pwd):
    """Creates a new, empty database."""

    connection = pymysql.connect(host = "localhost",
                                 user = user,
                                 password = pwd,
                                 cursorclass = pymysql.cursors.DictCursor)
    cur = connection.cursor()

    # First, test if a test database already exists within mysql.
    # If there is, delete it so that a fresh test database is installed.
    sql = ("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
          f"WHERE SCHEMA_NAME = '{db}'")
    cur.execute(sql)
    result = cur.fetchall()
    if len(result) != 0:
        cur.execute(f"DROP DATABASE {db}")
        connection.commit()

    # Next, create the database within mysql.
    cur.execute(f"CREATE DATABASE {db}")
    connection.commit()
    connection.close()

    # Now import the empty schema from file.
    # Seems like pymysql has trouble with this step, so use subprocess.
    handle = open(schema_filepath, "r")
    command_string = f"mysql -u {user} -p{pwd} {db}"
    command_list = command_string.split(" ")
    proc = subprocess.check_call(command_list, stdin = handle)
    handle.close()




def remove_db(db, user, pwd):
    """Remove the MySQL database created for the test."""
    connection = pymysql.connect(host="localhost",
                                 user=user,
                                 password=pwd,
                                 cursorclass=pymysql.cursors.DictCursor)
    cur = connection.cursor()
    cur.execute(f"DROP DATABASE {db}")
    connection.commit()
    connection.close()


def insert_data_into_phage_table(db, user, pwd, data_dict):
    """Insert data into the phage table."""
    connection = pymysql.connect(host = "localhost",
                                 user = user,
                                 password = pwd,
                                 database = db,
                                 cursorclass = pymysql.cursors.DictCursor)
    cur = connection.cursor()
    sql = (
        "INSERT INTO phage "
        "(PhageID, Accession, Name, "
        "HostStrain, Sequence, SequenceLength, GC, status, "
        "DateLastModified, RetrieveRecord, AnnotationAuthor, "
        "Cluster, Cluster2, Subcluster2) "
        "VALUES ("
        f"'{data_dict['PhageID']}', '{data_dict['Accession']}', "
        f"'{data_dict['Name']}', '{data_dict['HostStrain']}', "
        f"'{data_dict['Sequence']}', {data_dict['SequenceLength']}, "
        f"{data_dict['GC']}, '{data_dict['status']}', "
        f"'{data_dict['DateLastModified']}', "
        f"{data_dict['RetrieveRecord']}, "
        f"{data_dict['AnnotationAuthor']}, '{data_dict['Cluster']}', "
        f"'{data_dict['Cluster2']}', '{data_dict['Subcluster2']}');"
        )
    cur.execute(sql)
    connection.commit()
    connection.close()


def insert_data_into_gene_table(db, user, pwd, data_dict):
    """Insert data into the gene table."""
    connection = pymysql.connect(host = "localhost",
                                 user = user,
                                 password = pwd,
                                 database = db,
                                 cursorclass = pymysql.cursors.DictCursor)
    cur = connection.cursor()
    sql = (
        "INSERT INTO gene "
        "(GeneID, PhageID, Start, Stop, Length, Name, "
        "translation, Orientation, Notes, LocusTag) "
        "VALUES ("
        f"'{data_dict['GeneID']}', '{data_dict['PhageID']}', "
        f"{data_dict['Start']}, {data_dict['Stop']}, "
        f"{data_dict['Length']}, '{data_dict['Name']}', "
        f"'{data_dict['translation']}', '{data_dict['Orientation']}', "
        f"'{data_dict['Notes']}', '{data_dict['LocusTag']}');"
        )
    cur.execute(sql)
    connection.commit()
    connection.close()


# TODO this may no longer be needed.
# def modify_sql_field(db, user, pwd, table,
#                      new_field, new_value,
#                      ref_field, ref_value):
#     """Insert data into a specified field in the specified table."""
#     connection = pymysql.connect(host = "localhost",
#                                  user = user,
#                                  password = pwd,
#                                  database = db)
#     cur = connection.cursor()
#     sql = (
#         f"UPDATE {table} SET {new_field} = '{new_value}' "
#         f"WHERE {ref_field} = '{ref_value}';"
#         )
#     cur.execute(sql)
#     connection.commit()
#     connection.close()



phage_table_query = (
    "SELECT "
    "PhageID, Accession, Name, "
    "HostStrain, Sequence, SequenceLength, GC, status, "
    "DateLastModified, RetrieveRecord, AnnotationAuthor, "
    "Cluster, Cluster2, Subcluster2 "
    "FROM phage;"
    )

gene_table_query = (
    "SELECT "
    "GeneID, PhageID, Start, Stop, Length, Name, "
    "translation, Orientation, Notes, LocusTag "
    "FROM gene;"
)





def get_sql_data(db, user, pwd, query):
    """Get data from the database."""
    connection = pymysql.connect(host = "localhost",
                                 user = user,
                                 password = pwd,
                                 database = db,
                                 cursorclass = pymysql.cursors.DictCursor)
    cur = connection.cursor()
    cur.execute(query)
    results = cur.fetchall()
    cur.close()
    connection.close()
    return results


def process_phage_table_data(list_of_sql_results):
    """."""
    x = 0
    while x < len(list_of_sql_results):
        data_dict = list_of_sql_results[x]
        # print(data_dict.keys())
        # input("pause")
        data_dict["Sequence"] = data_dict["Sequence"].decode("utf-8")
        data_dict["SequenceLength"] = int(data_dict["SequenceLength"])
        # data_dict["Notes"] = data_dict["Notes"].decode("utf-8")
        data_dict["GC"] = float(data_dict["GC"])
        x += 1


def process_gene_table_data(list_of_sql_results):
    """."""
    x = 0
    while x < len(list_of_sql_results):
        data_dict = list_of_sql_results[x]
        data_dict["Notes"] = data_dict["Notes"].decode("utf-8")
        data_dict["Length"] = int(data_dict["Length"])
        data_dict["Start"] = int(data_dict["Start"])
        data_dict["Stop"] = int(data_dict["Stop"])
        x += 1

def filter_genome_data(list_of_sql_results, phage_id):
    """."""
    x = 0
    output_dict = {}
    while x < len(list_of_sql_results):
        if list_of_sql_results[x]["PhageID"] == phage_id:
            output_dict = list_of_sql_results[x]
        else:
            pass
        x += 1
    return output_dict



def filter_gene_data(list_of_sql_results, coordinates):
    """."""
    x = 0
    output_dict = {}
    while x < len(list_of_sql_results):
        if (list_of_sql_results[x]["Start"] == coordinates[0] and
                list_of_sql_results[x]["Stop"] == coordinates[1]):
            output_dict = list_of_sql_results[x]
        else:
            pass
        x += 1

    return output_dict



def compare_data(ref_dict, query_dict):
    """Ref dictionary = the expected data.
    Query dictionary = the data retrieved from the database."""
    x = 0
    errors = 0
    for key in ref_dict.keys():
        exp_value = ref_dict[key]
        query_value = query_dict[key]
        if exp_value != query_value:
            errors += 1
            print(key)
            print(exp_value)
            print(query_value)
            input("check value")
    return errors

def get_seq(filepath):
    """Get genome sequence from a flat file so that it can be added
    to a MySQL database for testing."""
    seqrecord = SeqIO.read(filepath, "genbank")
    return seqrecord.seq



def get_l5_phage_table_data():
    """."""
    dict = {
        "PhageID": "L5",
        "Accession": "ABC123",
        "Name": "L5",
        "HostStrain": "Mycobacterium",
        "Sequence": "AAAAAAAAAA",
        "SequenceLength": 10,
        "GC": 0,
        "status": "final",
        "DateLastModified": datetime.strptime('1/1/0001', '%m/%d/%Y'),
        "RetrieveRecord": 1,
        "AnnotationAuthor": 1,
        "Cluster": "A2",
        "Cluster2": "A",
        "Subcluster2": "A2"
        }
    return dict




def get_trixie_phage_table_data():
    """."""
    dict = {
        "PhageID": "Trixie",
        "Accession": "BCD456",
        "Name": "Trixie",
        "HostStrain": "Gordonia",
        "Sequence": "GGGGGGGGGGGGGGGGGGGG",
        "SequenceLength": 20,
        "GC": 1,
        "status": "final",
        "DateLastModified": datetime.strptime('1/1/2000', '%m/%d/%Y'),
        "RetrieveRecord": 1,
        "AnnotationAuthor": 1,
        "Cluster": "A3",
        "Cluster2": "A",
        "Subcluster2": "A3"
        }
    return dict


def get_redrock_phage_table_data():
    """."""
    dict = {
        "PhageID": "RedRock",
        "Accession": "BCD456",
        "Name": "RedRock_Draft",
        "HostStrain": "Arthrobacter",
        "Sequence": "CCCCCCCCCCCCCCC",
        "SequenceLength": 15,
        "GC": 1,
        "status": "draft",
        "DateLastModified": datetime.strptime('1/1/2010', '%m/%d/%Y'),
        "RetrieveRecord": 1,
        "AnnotationAuthor": 1,
        "Cluster": "B1",
        "Cluster2": "B",
        "Subcluster2": "B1"
        }
    return dict


def get_d29_phage_table_data():
    """."""
    dict = {
        "PhageID": "D29",
        "Accession": "XYZ123",
        "Name": "D29",
        "HostStrain": "Microbacterium",
        "Sequence": "ATGCATGCATGCATGC",
        "SequenceLength": 16,
        "GC": 0.5,
        "status": "unknown",
        "DateLastModified": datetime.strptime('1/1/0001', '%m/%d/%Y'),
        "RetrieveRecord": 0,
        "AnnotationAuthor": 0,
        "Cluster": "D1",
        "Cluster2": "D",
        "Subcluster2": "D1"
        }
    return dict


def get_trixie_gene_table_data_1():
    """."""
    dict = {
        "GeneID": "TRIXIE_0001",
        "PhageID": "Trixie",
        "Start": 100,
        "Stop": 1100,
        "Length": 1000,
        "Name": "1",
        "translation": "ACTGC",
        "Orientation": "F",
        "Notes": "int",
        "LocusTag": "SEA_TRIXIE_0001"
        }
    return dict

def create_min_tkt_dict(old_tkt):

    min_keys = set(["id", "type", "phage_id"])
    new_tkt = {}
    for key in min_keys:
        new_tkt[key] = old_tkt[key]
    return new_tkt

def set_data(old_tkt, keys, value):
    """Set selected keys to certain values."""
    new_tkt = old_tkt.copy()
    for key in keys:
        new_tkt[key] = value
    return new_tkt




def get_l5_ticket_data_complete():
    """Returns a dictionary of ticket data for L5."""
    dict = {
        "id": 1,
        "type": "add",
        "phage_id": "L5",
        "host_genus": "Mycobacterium",
        "cluster": "A",
        "subcluster": "A2",
        "accession": "ABC123",
        "description_field": "product",
        "annotation_status": "draft",
        "annotation_author": 1,
        "retrieve_record": 1,
        "run_mode": "phagesdb"
        }
    return dict




def get_alice_ticket_data_complete():
    """Returns a dictionary of ticket data for Alice."""
    dict = {
        "id": 1,
        "type": "add",
        "phage_id": "Alice",
        "host_genus": "Mycobacterium",
        "cluster": "C",
        "subcluster": "C1",
        "accession": "none",
        "description_field": "product",
        "annotation_status": "draft",
        "annotation_author": 1,
        "retrieve_record": 1,
        "run_mode": "pecaan"
        }
    return dict





# TODO these variables may no longer be needed.
l5_ticket_data_min = create_min_tkt_dict(get_l5_ticket_data_complete())

valid_retrieve_keys = set(["host_genus", "cluster", "subcluster", "accession"])
l5_ticket_data_retrieve = set_data(get_l5_ticket_data_complete(), valid_retrieve_keys, "retrieve")

valid_retain_keys = set(["host_genus", "cluster", "subcluster",
                         "accession", "annotation_author", "retrieve_record"])
# TODO these variables may no longer be needed.






def create_import_table(list_of_data_dicts, file_path):
    """Create an import table."""

    headers = set()
    for dict in list_of_data_dicts:
        headers = headers | dict.keys()

    headers_dict = {}
    for header in headers:
        headers_dict[header] = header
    with open(file_path, "w") as file_handle:
        file_writer = csv.DictWriter(file_handle, headers)
        file_writer.writerow(headers_dict)
        for data_dict in list_of_data_dicts:
            file_writer.writerow(data_dict)




def clear_descriptions(record):
    """Remove descriptions from CDS features."""
    x = 0
    while x < len(record.features):
        feature = record.features[x]
        if feature.type == "CDS":
            if "product" in feature.qualifiers.keys():
                feature.qualifiers["product"] = [""]
            if "function" in feature.qualifiers.keys():
                feature.qualifiers["function"] = [""]
            if "note" in feature.qualifiers.keys():
                feature.qualifiers["note"] = [""]
        x += 1







def get_alice_genome_draft_data_in_db():
    """."""
    genome_seq = get_seq(base_flat_file_path)
    data_dict = {
        "PhageID": "Alice",
        "Accession": "",
        "Name": "Alice_Draft",
        "HostStrain": "Mycobacterium",
        "Sequence": genome_seq,
        "SequenceLength": 153401,
        "GC": 64.6808,
        "status": "draft",
        "DateLastModified": current_date,
        "RetrieveRecord": 1,
        "AnnotationAuthor": 1,
        "Cluster": "C1",
        "Cluster2": "C",
        "Subcluster2": "C1"
        }
    return data_dict



def get_alice_genome_final_data_in_db():
    """."""
    # Get default draft genome data
    data_dict = get_alice_genome_draft_data_in_db()

    # Set certain values for 'draft' genome.
    data_dict["Name"] = "Alice"
    data_dict["Accession"] = "JF704092"
    data_dict["status"] = "final"
    data_dict["DateLastModified"] = current_date
    # data_dict["DateLastModified"] = datetime.strptime('3/23/2018', '%m/%d/%Y')
    return data_dict



def get_unparsed_draft_import_args():
    """."""
    unparsed_args = ["run.py", pipeline, db,
                      str(genome_folder),
                      str(import_table),
                      "-g", "_organism_name",
                      "-p",
                      "-r", "pecaan",
                      "-d", "product",
                      "-o", str(output_folder),
                      "-l", str(log_file)
                      ]
    return unparsed_args

def get_unparsed_final_import_args():
    """."""
    unparsed_args = ["run.py", pipeline, db,
                      str(genome_folder),
                      str(import_table),
                      "-g", "_organism_name",
                      "-p",
                      "-r", "phagesdb",
                      "-d", "product",
                      "-o", str(output_folder),
                      "-l", str(log_file)
                      ]
    return unparsed_args




alice_cds_252_translation = (
    "MFDNHPLMSTLITSVRDLNRLANGVIIRNRCEKCDTSAGPDQGV"
    "HFVKTPLGWLYSDPKGKPTTWELFPSDAIHLPVQVIHRVSESEDVSEITENSPHTRKD"
    "DSEATEGAAPSFEPLYPSSHKTERFTVQDTPDGLGAYVFDFGGDAFGAQTCADALAKV"
    "TGKTWYVMHKTVVENTGIYSSMVRHEEESSS")

def get_alice_cds_252_draft_data_in_db(translation=alice_cds_252_translation):
    """."""
    dict = {
        "GeneID": "Alice_CDS_4",
        "PhageID": "Alice",
        "Start": 152829,
        "Stop": 4,
        "Length": 191,
        "Name": "252",
        "translation": translation,
        "Orientation": "F",
        "Notes": "",
        "LocusTag": ""
        }
    return dict

def get_alice_cds_252_final_data_in_db():
    """."""
    dict = get_alice_cds_252_draft_data_in_db()
    dict["LocusTag"] = "ALICE_252"
    return dict




alice_cds_124_translation = (
    "MKDEMTTSDVPADPAIDPDLAPPEPRRVVGELVETEPQEHEDPEVTELTDEERSSFVSLLT"
    "CGKHSKKITVMGHPVVIQTLKTGDEMRVGLFTKKYLESQMGFQRAYQVAVCAAGIREIQGK"
    "PLFRELREVTDEDEIFDKNVEAVMELYPIVITQIYQAIMDLEREYAQLAVKLGKTVRLDAS"
    "TELEIRLAYKQGLLTQPSLNRYQRWALRYAIFMDRRLQLQDTEDMLQRQTWYLEPKRYHDL"
    "FLAGAFEPEPIAVAGRDMEEVVDDLDEVDAYFARLEGSQSMSGAQLFAALDEPDEEGWM"
    )

def get_alice_cds_124_draft_data_in_db(translation=alice_cds_124_translation):
    """."""
    dict = {
        "GeneID": "Alice_CDS_1",
        "PhageID": "Alice",
        "Start": 70374,
        "Stop": 71285,
        "Length": 303,
        "Name": "124",
        "translation": translation,
        "Orientation": "F",
        "Notes": "",
        "LocusTag": ""
        }
    return dict

def get_alice_cds_124_final_data_in_db():
    """."""
    dict = get_alice_cds_124_draft_data_in_db()
    dict["LocusTag"] = "ALICE_124"
    dict["Notes"] = "tail assembly chaperone"
    return dict




alice_cds_139_translation = (
    "MKKLVTGGLVAAGITLGLISAPSASAEYMTICPSQVSAVVTANTSCGFADNV"
    "FRGFYRQSGWDPLAYSPATGKVYRMHCAPATTTNWGEAKRCWGVGYGGDLLVVYID"
    )

def get_alice_cds_139_draft_data_in_db(translation=alice_cds_139_translation):
    """."""
    dict = {
        "GeneID": "Alice_CDS_2",
        "PhageID": "Alice",
        "Start": 88120,
        "Stop": 88447,
        "Length": 108,
        "Name": "139",
        "translation": translation,
        "Orientation": "R",
        "Notes": "",
        "LocusTag": ""
        }
    return dict

def get_alice_cds_139_final_data_in_db():
    """."""
    dict = get_alice_cds_139_draft_data_in_db()
    dict["LocusTag"] = "ALICE_139"
    return dict









alice_cds_193_translation = (
    "MGNNRPTTRTLPTGEKATHHPDGRLVLKPKNSLADALSGQLDAQQEASQALTEALV"
    "QTAVTKREAQADGNPVPEDKRVF"
    )

def get_alice_cds_193_draft_data_in_db(translation=alice_cds_193_translation):
    """."""
    dict = {
        "GeneID": "Alice_CDS_3",
        "PhageID": "Alice",
        "Start": 110297,
        "Stop": 110537,
        "Length": 79,
        "Name": "193",
        "translation": translation,
        "Orientation": "F",
        "Notes": "",
        "LocusTag": ""
        }
    return dict


def get_alice_cds_193_final_data_in_db():
    """."""
    dict = get_alice_cds_193_draft_data_in_db()
    dict["LocusTag"] = "ALICE_193"
    return dict



alice_cds_252_coords = (152829, 4)
alice_cds_124_coords = (70374, 71285)
alice_cds_139_coords = (88120, 88447)
alice_cds_193_coords = (110297, 110537)



def get_alice_cds_252_qualifier_dict():
    """."""
    dict = OrderedDict(
            [("gene", ["252"]),
             ("locus_tag", ["ALICE_252"]),
             ("note", ["gp252"]),
             ("codon_start", ["1"]),
             ("transl_table", ["11"]),
             ("product", ["hypothetical protein"]),
             ("protein_id", ["AEJ94474.1"]),
             ("translation", [])])
    return dict



def get_alice_cds_252_seqfeature():
    """."""
    seq_ftr = SeqFeature(
                CompoundLocation(
                    [FeatureLocation(
                        ExactPosition(152829),
                        ExactPosition(153401),
                        strand=1),
                    FeatureLocation(
                        ExactPosition(0),
                        ExactPosition(4),
                        strand=1)],
                    "join"),
                type="CDS",
                location_operator="join")
    return seq_ftr

def get_alice_cds_124_qualifier_dict():
    """."""
    dict = OrderedDict(
        [("gene", ["124"]),
         ("locus_tag", ["ALICE_124"]),
         ("ribosomal_slippage", [""]),
         ("note", ["gp124"]),
         ("codon_start", ["1"]),
         ("transl_table", ["11"]),
         ("product", [""]),
         # ("product", ["tail assembly chaperone"]),
         ("protein_id", ["AEJ94379.1"]),
         ("translation", [])])
    return dict



def get_alice_cds_124_seqfeature():
    """."""
    seq_ftr = SeqFeature(
                CompoundLocation(
                    [FeatureLocation(
                        ExactPosition(70374),
                        ExactPosition(70902),
                        strand=1),
                    FeatureLocation(
                        ExactPosition(70901),
                        ExactPosition(71285),
                        strand=1)],
                    "join"),
                type="CDS",
                location_operator="join")
    return seq_ftr




def get_alice_cds_139_qualifier_dict():
    """."""
    dict = OrderedDict(
            [("gene", ["139"]),
             ("locus_tag", ["ALICE_139"]),
             ("note", ["gp139"]),
             ("codon_start", ["1"]),
             ("transl_table", ["11"]),
             ("product", ["hypothetical protein"]),
             ("protein_id", ["AEJ94477.1"]),
             ("translation", [])])
    return dict


def get_alice_cds_139_seqfeature():
    """."""
    seq_ftr = SeqFeature(
                FeatureLocation(
                    ExactPosition(88120),
                    ExactPosition(88447),
                    strand=-1),
                type="CDS")
    return seq_ftr





def get_alice_cds_193_qualifier_dict():
    """."""
    dict = OrderedDict(
            [("gene", ["193"]),
             ("locus_tag", ["ALICE_193"]),
             ("note", ["gp193"]),
             ("codon_start", ["1"]),
             ("transl_table", ["11"]),
             ("product", ["hypothetical protein"]),
             ("protein_id", ["AEJ94419.1"]),
             ("translation", [])])
    return dict


def get_alice_cds_193_seqfeature():
    """."""
    seq_ftr = SeqFeature(
                FeatureLocation(
                    ExactPosition(110297),
                    ExactPosition(110537),
                    strand=1),
                type="CDS")
    return seq_ftr



def get_alice_tmrna_169_qualifier_dict():
    """."""
    dict = OrderedDict(
            [('gene', ['169']),
             ('locus_tag', ['ALICE_169'])])
    return dict




def get_alice_tmrna_169():
    """."""
    seq_ftr = SeqFeature(
                FeatureLocation(
                    ExactPosition(95923),
                    ExactPosition(96358),
                    strand=1),
                type="tmRNA")
    return seq_ftr



def get_alice_trna_170_qualifier_dict():
    """."""
    dict = OrderedDict(
            [('gene', ['170']),
             ('locus_tag', ['ALICE_170']),
             ('product', ['tRNA-Gln']),
             ('note', ['tRNA-Gln (ttg)'])])
    return dict

def get_alice_trna_170():
    """."""
    seq_ftr = SeqFeature(
                FeatureLocation(
                    ExactPosition(96431),
                    ExactPosition(96507),
                    strand=1),
                type="tRNA")
    return seq_ftr





def get_alice_source_1_qualifiers():
    """."""
    dict = OrderedDict(
            [("organism", ["Mycobacterium phage Alice_Draft"]),
             ("mol_type", ["genomic DNA"]),
             ("isolation_source", ["soil"]),
             ("db_xref", ["taxon:1034128"]),
             ("lab_host", ["Mycobacterium smegmatis mc2 155"]),
             ("country", ["USA: Aledo, TX"]),
             ("lat_lon", ["31.69 N 97.65 W"]),
             ("collection_date", ["01-Oct-2009"]),
             ("collected_by", ["C. Manley"]),
             ("identified_by", ["C. Manley"])])
    return dict



def get_alice_source_1():
    """."""
    seq_ftr = SeqFeature(
                FeatureLocation(
                    ExactPosition(0),
                    ExactPosition(153401),
                    strand=1),
                type="source")
    return seq_ftr



author_string_1 = "Hatfull,G.F."
author_string_2 = (
    "Alferez,G.I., Bryan,W.J., Byington,E.L., Contreras,T.D., "
    "Evans,C.R., Griffin,J.A., Jalal,M.D., Lindsey,C.B., "
    "Manley,C.M., Mitchell,A.M., O'Hara,J.M., Onoh,U.M., "
    "Padilla,E., Penrod,L.C., Regalado,M.S., Reis,K.E., "
    "Ruprecht,A.M., Slater,A.E., Staton,A.C., Tovar,I.G., "
    "Turek,A.J., Utech,N.T., Simon,S.E., Hughes,L.E., "
    "Benjamin,R.C., Serrano,M.G., Lee,V., Hendricks,S.L., "
    "Sheth,N.U., Buck,G.A., Bradley,K.W., Khaja,R., "
    "Lewis,M.F., Barker,L.P., Jordan,T.C., Russell,D.A., "
    "Leuba,K.D., Fritz,M.J., Bowman,C.A., Pope,W.H., "
    "Jacobs-Sera,D., Hendrix,R.W. and Hatfull,G.F.")






class TestImportGenomeMain1(unittest.TestCase):
    """Tests involving trying to add a 'draft' genome into the database."""

    def setUp(self):
        create_new_db(schema_file, db, user, pwd)
        base_dir.mkdir()
        genome_folder.mkdir()
        output_folder.mkdir()


        # Construct minimal Alice genome
        # CDS 252 is a wrap-around compound gene.
        # CDS 124 is a compound feature.
        # CDS 193 is a normal CDS.
        # CDS 139 is a normal CDS.
        self.alice_cds_252_translation = alice_cds_252_translation
        self.alice_cds_252_qualifier_dict = get_alice_cds_252_qualifier_dict()
        self.alice_cds_252_qualifier_dict["translation"] = \
            [self.alice_cds_252_translation]
        self.alice_cds_252 = get_alice_cds_252_seqfeature()
        self.alice_cds_252.qualifiers = self.alice_cds_252_qualifier_dict

        self.alice_cds_124_translation = alice_cds_124_translation
        self.alice_cds_124_qualifier_dict = get_alice_cds_124_qualifier_dict()
        self.alice_cds_124_qualifier_dict["translation"] = \
            [self.alice_cds_124_translation]
        self.alice_cds_124 = get_alice_cds_124_seqfeature()
        self.alice_cds_124.qualifiers = self.alice_cds_124_qualifier_dict

        self.alice_cds_139_translation = alice_cds_139_translation
        self.alice_cds_139_qualifier_dict = get_alice_cds_139_qualifier_dict()
        self.alice_cds_139_qualifier_dict["translation"] = \
            [self.alice_cds_139_translation]
        self.alice_cds_139 = get_alice_cds_139_seqfeature()
        self.alice_cds_139.qualifiers = self.alice_cds_139_qualifier_dict

        self.alice_cds_193_translation = alice_cds_193_translation
        self.alice_cds_193_qualifier_dict = get_alice_cds_193_qualifier_dict()
        self.alice_cds_193_qualifier_dict["translation"] = \
            [self.alice_cds_193_translation]
        self.alice_cds_193 = get_alice_cds_193_seqfeature()
        self.alice_cds_193.qualifiers = self.alice_cds_193_qualifier_dict

        self.alice_tmrna_169_qualifier_dict = get_alice_tmrna_169_qualifier_dict()
        self.alice_tmrna_169 = get_alice_tmrna_169()
        self.alice_tmrna_169.qualifiers = self.alice_tmrna_169_qualifier_dict

        self.alice_trna_170_qualifier_dict = get_alice_trna_170_qualifier_dict()
        self.alice_trna_170 = get_alice_trna_170()
        self.alice_trna_170.qualifiers = self.alice_trna_170_qualifier_dict

        self.alice_source_1_qualifiers = get_alice_source_1_qualifiers()
        self.alice_source_1 = get_alice_source_1()
        self.alice_source_1.qualifiers = self.alice_source_1_qualifiers

        self.alice_feature_list = [self.alice_source_1,
                                   self.alice_cds_252, # Wrap around gene
                                   self.alice_cds_124, # Compound gene
                                   self.alice_cds_139, # Bottom strand normal CDS
                                   self.alice_tmrna_169,
                                   self.alice_trna_170,
                                   self.alice_cds_193 # Top strand normal CDS
                                   ]

        self.alice_ref1 = Reference()
        self.alice_ref1.authors = author_string_1
        self.alice_ref2 = Reference()
        self.alice_ref2.authors = author_string_2
        self.alice_ref_list = [self.alice_ref1, self.alice_ref2]

        self.alice_description = ("Mycobacterium phage Alice_Draft, "
                                  "complete sequence")
        self.alice_organism = "Mycobacterium phage Alice_Draft"
        self.alice_source = "Mycobacterium phage Alice_Draft"
        self.alice_date = "23-MAR-2018"
        self.alice_accessions = [""]
        self.alice_annotation_dict = {
            "accessions": self.alice_accessions,
            "source": self.alice_source,
            "organism": self.alice_organism,
            "references": self.alice_ref_list,
            "date": self.alice_date}
        self.alice_seq = get_seq(base_flat_file_path)
        self.alice_record = SeqRecord(
                                seq = self.alice_seq,
                                id = "",
                                name = "JF704092",
                                annotations = self.alice_annotation_dict,
                                description = self.alice_description,
                                features = self.alice_feature_list
                                )

        # Get data to set up import table.
        self.alice_ticket = get_alice_ticket_data_complete()

        # Get data to run the entire pipeline.
        self.unparsed_args = get_unparsed_draft_import_args()



    def tearDown(self):
        shutil.rmtree(base_dir)
        remove_db(db, user, pwd)

        # This removes the default output folder in the 'tmp'
        # directory, which gets created if no output folder is
        # indicated at the command line, which occurs in some tests below.
        if default_output_path.exists() == True:
            shutil.rmtree(default_output_path)




    @patch("getpass.getpass")
    def test_import_pipeline_1(self, getpass_mock):
        """Test pipeline with:
        valid add ticket for draft genome,
        no data in the database."""
        logging.info("test_import_pipeline_1")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 4)
        with self.subTest():
            self.assertFalse(alice_flat_file_path.exists())
        with self.subTest():
            self.assertTrue(success_alice_path.exists())
        with self.subTest():
            self.assertTrue(success_table_path.exists())
        with self.subTest():
            self.assertFalse(fail_path.exists())
        with self.subTest():
            self.assertEqual(phage_table_results[0]["PhageID"], "Alice")
        with self.subTest():
            self.assertEqual(phage_table_results[0]["Name"], "Alice_Draft")


        # Note: testing whether the log file exists is tricky,
        # due to how the logging module operates.
        # with self.subTest():
        #     self.assertTrue(self.log_file.exists())


    @patch("getpass.getpass")
    def test_import_pipeline_2(self, getpass_mock):
        """Test pipeline with:
        valid add ticket for draft genome,
        valid flat file,
        non-Alice data already in the database."""
        logging.info("test_import_pipeline_2")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, get_d29_phage_table_data())
        insert_data_into_phage_table(db, user, pwd, get_redrock_phage_table_data())
        insert_data_into_phage_table(db, user, pwd, get_trixie_phage_table_data())
        insert_data_into_gene_table(db, user, pwd, get_trixie_gene_table_data_1())
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        expected_phage_table_data = get_alice_genome_draft_data_in_db()
        genome_errors = compare_data(expected_phage_table_data,
                                     output_genome_data)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        process_gene_table_data(gene_table_results)

        cds252_data = filter_gene_data(gene_table_results, alice_cds_252_coords)
        cds124_data = filter_gene_data(gene_table_results, alice_cds_124_coords)
        cds139_data = filter_gene_data(gene_table_results, alice_cds_139_coords)
        cds193_data = filter_gene_data(gene_table_results, alice_cds_193_coords)

        expected_cds252_data = get_alice_cds_252_draft_data_in_db()
        expected_cds124_data = get_alice_cds_124_draft_data_in_db()
        expected_cds139_data = get_alice_cds_139_draft_data_in_db()
        expected_cds193_data = get_alice_cds_193_draft_data_in_db()

        cds252_errors = compare_data(expected_cds252_data, cds252_data)
        cds124_errors = compare_data(expected_cds124_data, cds124_data)
        cds139_errors = compare_data(expected_cds139_data, cds139_data)
        cds193_errors = compare_data(expected_cds193_data, cds193_data)

        with self.subTest():
            self.assertEqual(len(phage_table_results), 4)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 5)
        with self.subTest():
            self.assertEqual(genome_errors, 0)
        with self.subTest():
            self.assertEqual(cds252_errors, 0)
        with self.subTest():
            self.assertEqual(cds124_errors, 0)
        with self.subTest():
            self.assertEqual(cds139_errors, 0)
        with self.subTest():
            self.assertEqual(cds193_errors, 0)


    @patch("getpass.getpass")
    def test_import_pipeline_3(self, getpass_mock):
        """Test pipeline with:
        valid add ticket for draft genome,
        no data in the database, minimal command line arguments."""
        logging.info("test_import_pipeline_3")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        unparsed_args = ["run.py", pipeline, db,
                         str(genome_folder),
                         str(import_table),
                         "-p",
                         ]
        run.main(unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 4)


    @patch("getpass.getpass")
    def test_import_pipeline_4(self, getpass_mock):
        """Test pipeline with:
        valid minimal add ticket for draft genome,
        no data in the database."""
        logging.info("test_import_pipeline_4")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        alice_min_ticket = create_min_tkt_dict(self.alice_ticket)
        create_import_table([alice_min_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 4)


    @patch("getpass.getpass")
    def test_import_pipeline_5(self, getpass_mock):
        """Test pipeline with:
        valid add ticket for draft genome,
        no data in the database,
        no production run."""
        logging.info("test_import_pipeline_5")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        unparsed_args = ["run.py", pipeline, db,
                         str(genome_folder),
                         str(import_table),
                         "-o", str(output_folder)
                         ]
        run.main(unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 0)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_305(self, getpass_mock):
        """Test pipeline with:
        valid add for draft genome, and genome name in the flat file
        does not contain 'draft' suffix and multiple locations.
        no data in the database."""
        logging.info("test_import_pipeline_305")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_source_1.qualifiers["organism"] = ["Mycobacterium phage Alice"]
        self.alice_description = "Mycobacterium phage Alice, complete sequence"
        self.alice_organism = "Mycobacterium phage Alice"
        self.alice_source = "Mycobacterium phage Alice"
        self.alice_annotation_dict["organism"] = self.alice_organism
        self.alice_annotation_dict["source"] = self.alice_source
        self.alice_record.annotations = self.alice_annotation_dict
        self.alice_record.description = self.alice_description
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 1)


    @patch("getpass.getpass")
    def test_import_pipeline_290(self, getpass_mock):
        """Test pipeline with:
        valid add ticket with uncommon values (case changes, "none", "")
        for draft genome, no data in the database."""
        logging.info("test_import_pipeline_290")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["host_genus"] = "RETRIEVE"
        self.alice_ticket["accession"] = ""
        self.alice_ticket.pop("cluster")
        self.alice_ticket["subcluster"] = "NONE"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        with self.subTest():
            self.assertEqual(phage_table_results[0]["Accession"], "")
        with self.subTest():
            self.assertEqual(phage_table_results[0]["HostStrain"], "Mycobacterium")
        with self.subTest():
            self.assertEqual(phage_table_results[0]["Cluster2"], "C")
        with self.subTest():
            self.assertEqual(phage_table_results[0]["Cluster"], "C")
        with self.subTest():
            self.assertIsNone(phage_table_results[0]["Subcluster2"])


    @patch("getpass.getpass")
    def test_import_pipeline_300(self, getpass_mock):
        """Test pipeline with:
        valid add ticket setting Cluster as Singleton for draft genome,
        no data in the database."""
        logging.info("test_import_pipeline_300")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["cluster"] = "Singleton"
        self.alice_ticket["subcluster"] = "none"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        with self.subTest():
            self.assertIsNone(phage_table_results[0]["Cluster2"])
        with self.subTest():
            self.assertIsNone(phage_table_results[0]["Cluster"])
        with self.subTest():
            self.assertIsNone(phage_table_results[0]["Subcluster2"])







    # Run tests using tickets structured incorrectly.
    @patch("pdm_utils.pipelines.db_import.import_genome.process_files_and_tickets")
    @patch("sys.exit")
    @patch("getpass.getpass")
    def test_import_pipeline_6(self, getpass_mock, sys_exit_mock, pft_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid run_mode."""
        logging.info("test_import_pipeline_6")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["run_mode"] = "invalid"
        create_import_table([self.alice_ticket], import_table)
        pft_mock.return_value = ([], [], [], [], [])
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 0)
        with self.subTest():
            self.assertTrue(alice_flat_file_path.exists())
        with self.subTest():
            self.assertFalse(success_path.exists())
        with self.subTest():
            self.assertFalse(fail_path.exists())


    @patch("pdm_utils.pipelines.db_import.import_genome.process_files_and_tickets")
    @patch("sys.exit")
    @patch("getpass.getpass")
    def test_import_pipeline_7(self, getpass_mock, sys_exit_mock, pft_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid description_field."""
        logging.info("test_import_pipeline_7")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["description_field"] = "invalid"
        create_import_table([self.alice_ticket], import_table)
        pft_mock.return_value = ([], [], [], [], [])
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)


    @patch("pdm_utils.pipelines.db_import.import_genome.process_files_and_tickets")
    @patch("sys.exit")
    @patch("getpass.getpass")
    def test_import_pipeline_8(self, getpass_mock, sys_exit_mock, pft_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid ticket type."""
        logging.info("test_import_pipeline_8")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["type"] = "invalid"
        create_import_table([self.alice_ticket], import_table)
        pft_mock.return_value = ([], [], [], [], [])
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)


    @patch("pdm_utils.pipelines.db_import.import_genome.process_files_and_tickets")
    @patch("sys.exit")
    @patch("getpass.getpass")
    def test_import_pipeline_303(self, getpass_mock, sys_exit_mock, pft_mock):
        """Test pipeline with:
        invalid add ticket with host_genus set to retain, even
        though the genome is not being replaced."""
        logging.info("test_import_pipeline_303")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["host_genus"] = "retain"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        with self.subTest():
            self.assertTrue(sys_exit_mock.called)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 0)


    @patch("pdm_utils.pipelines.db_import.import_genome.process_files_and_tickets")
    @patch("sys.exit")
    @patch("getpass.getpass")
    def test_import_pipeline_304(self, getpass_mock, sys_exit_mock, pft_mock):
        """Test pipeline with:
        invalid add ticket with retrieve set to retrieve, even
        though this data cannot be retrieved from PhagesDB."""
        logging.info("test_import_pipeline_304")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["retrieve_record"] = "retrieve"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        with self.subTest():
            self.assertTrue(sys_exit_mock.called)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 0)




    # Run tests that produce bundle check errors.
    @patch("getpass.getpass")
    def test_import_pipeline_9(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but incompatible annotation_status."""
        logging.info("test_import_pipeline_9")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["annotation_status"] = "final"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 0)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_10(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but phage_id is doesn't match the file."""
        logging.info("test_import_pipeline_10")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["phage_id"] = "Trixie"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)





    # Run tests that produce genome check errors.
    @patch("getpass.getpass")
    def test_import_pipeline_11(self, getpass_mock):
        """Test pipeline with:
        valid add ticket for draft genome,
        but Alice PhageID is already in database."""
        logging.info("test_import_pipeline_11")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        d29_phage_table_data = get_d29_phage_table_data()
        d29_phage_table_data["PhageID"] = "Alice"
        insert_data_into_phage_table(db, user, pwd, d29_phage_table_data)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)
        with self.subTest():
            self.assertFalse(alice_flat_file_path.exists())
        with self.subTest():
            self.assertFalse(success_path.exists())
        with self.subTest():
            self.assertTrue(fail_alice_path.exists())
        with self.subTest():
            self.assertTrue(fail_table_path.exists())


    @patch("getpass.getpass")
    def test_import_pipeline_12(self, getpass_mock):
        """Test pipeline with:
        valid add ticket for draft genome,
        but Alice genome sequence is already in database."""
        logging.info("test_import_pipeline_12")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        d29_phage_table_data = get_d29_phage_table_data()
        d29_phage_table_data["Sequence"] = str(self.alice_seq)
        insert_data_into_phage_table(db, user, pwd, d29_phage_table_data)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_13(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid cluster."""
        logging.info("test_import_pipeline_13")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["cluster"] = "ABCDE"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 0)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_14(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid subcluster."""
        logging.info("test_import_pipeline_14")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["subcluster"] = "A1234"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_15(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid host genus."""
        logging.info("test_import_pipeline_15")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["host_genus"] = "ABCDE"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)



    @patch("getpass.getpass")
    def test_import_pipeline_16(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid string annotation_author."""
        logging.info("test_import_pipeline_16")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["annotation_author"] = "invalid"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_17(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid integer annotation_author."""
        logging.info("test_import_pipeline_17")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["annotation_author"] = "3"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)

    @patch("getpass.getpass")
    def test_import_pipeline_18(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid retrieve_record."""
        logging.info("test_import_pipeline_18")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["retrieve_record"] = "3"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)

    @patch("getpass.getpass")
    def test_import_pipeline_19(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but invalid annotation_status."""
        logging.info("test_import_pipeline_19")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["annotation_status"] = "invalid"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_20(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but accession is present in the ticket."""
        logging.info("test_import_pipeline_20")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["accession"] = "ABC123"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)



    @patch("getpass.getpass")
    def test_import_pipeline_21(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but flat file has no CDS features."""
        logging.info("test_import_pipeline_21")
        getpass_mock.side_effect = [user, pwd]
        self.alice_record.features = [self.alice_source_1,
                                      self.alice_tmrna_169,
                                      self.alice_trna_170,
                                      ]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)




    @patch("getpass.getpass")
    def test_import_pipeline_22(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but flat file has CDS features with duplicate coordinates."""
        logging.info("test_import_pipeline_22")
        getpass_mock.side_effect = [user, pwd]
        self.alice_record.features = [self.alice_source_1,
                                      self.alice_tmrna_169,
                                      self.alice_trna_170,
                                      self.alice_cds_193,
                                      self.alice_cds_193
                                      ]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)



    @patch("getpass.getpass")
    def test_import_pipeline_23(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but flat file has genome with invalid '-' nucleotides."""
        logging.info("test_import_pipeline_23")
        getpass_mock.side_effect = [user, pwd]
        self.alice_seq = str(get_seq(base_flat_file_path))
        self.alice_seq = list(self.alice_seq)
        self.alice_seq[100] = "-"
        self.alice_seq = "".join(self.alice_seq)
        self.alice_seq = Seq(self.alice_seq, IUPAC.ambiguous_dna)
        self.alice_record = SeqRecord(
                                seq=self.alice_seq,
                                id="JF704092.1",
                                name="JF704092",
                                annotations=self.alice_annotation_dict,
                                description=self.alice_description,
                                features=self.alice_feature_list
                                )
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)



    @patch("getpass.getpass")
    def test_import_pipeline_24(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but flat file has genome with invalid 'Z' nucleotides."""
        logging.info("test_import_pipeline_24")
        getpass_mock.side_effect = [user, pwd]
        self.alice_seq = str(get_seq(base_flat_file_path))
        self.alice_seq = list(self.alice_seq)
        self.alice_seq[100] = "Z"
        self.alice_seq = "".join(self.alice_seq)
        self.alice_seq = Seq(self.alice_seq, IUPAC.ambiguous_dna)
        self.alice_record = SeqRecord(
                                seq=self.alice_seq,
                                id="JF704092.1",
                                name="JF704092",
                                annotations=self.alice_annotation_dict,
                                description=self.alice_description,
                                features=self.alice_feature_list
                                )
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)





    # Run tests that produce CDS check errors.
    @patch("getpass.getpass")
    def test_import_pipeline_25(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but flat file has CDS feature with incorrect amino acids."""
        logging.info("test_import_pipeline_25")
        # Note: the manual amino acid replacement to 'X' should throw at
        # least two errors: incorrect translation, and invalid amino acids.
        getpass_mock.side_effect = [user, pwd]
        alice_cds_193_translation_mod = list(self.alice_cds_193_translation)
        alice_cds_193_translation_mod[5] = "X"
        alice_cds_193_translation_mod = "".join(alice_cds_193_translation_mod)
        self.alice_cds_193_qualifier_dict["translation"] = [alice_cds_193_translation_mod]
        self.alice_record.features = [self.alice_cds_193]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)



    @patch("getpass.getpass")
    def test_import_pipeline_26(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but flat file has CDS feature with missing translation."""
        logging.info("test_import_pipeline_26")
        # Note: a missing translation should throw at
        # least two errors: incorrect translation, no translation present.
        getpass_mock.side_effect = [user, pwd]
        self.alice_cds_193_qualifier_dict["translation"] = []
        self.alice_record.features = [self.alice_cds_193]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_27(self, getpass_mock):
        """Test pipeline with:
        add ticket for draft genome
        but flat file has CDS feature with non-exact position."""
        logging.info("test_import_pipeline_27")
        getpass_mock.side_effect = [user, pwd]

        # In flat file, coordinates appear as:  "<110298..110537"
        alice_cds_193_mod = SeqFeature(
                                FeatureLocation(
                                    BeforePosition(110297),
                                    ExactPosition(110537),
                                    strand=1),
                                type="CDS",
                                qualifiers=self.alice_cds_193_qualifier_dict)

        self.alice_record.features = [alice_cds_193_mod]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        # input("check file")
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        self.assertEqual(len(phage_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_301(self, getpass_mock):
        """Test pipeline with:
        invalid add ticket with conflicting Cluster and Subcluster data,
        no data in the database."""
        logging.info("test_import_pipeline_301")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["cluster"] = "none"
        self.alice_ticket["subcluster"] = "C1"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 0)


    @patch("getpass.getpass")
    def test_import_pipeline_302(self, getpass_mock):
        """Test pipeline with:
        invalid add ticket with missing host genus data,
        no data in the database."""
        logging.info("test_import_pipeline_302")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_ticket["host_genus"] = "none"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 0)














        # Tests completed on Alice 'draft' genome:
        #1. insert alice w/1 CDS
        #2. try to insert alice if already in db
        #3. try to insert alice if another genome has same seq.
        #4. use invalid ticket
        #5. use minimal ticket.
        #6. fail due to genome-level error
        #7. fail due to CDS error.
        #8. test using oddly-strucutred ticket (uppercase, "none", empty, etc.)


            #
            # dict = {
            #     "id": 1,
            #     "type": "add",
            #     "phage_id": "Alice",
            #     "host_genus": "Mycobacterium",
            #     "cluster": "C",
            #     "subcluster": "C1",
            #     "accession": "none",
            #     "description_field": "product",
            #     "annotation_status": "draft",
            #     "annotation_author": 1,
            #     "retrieve_record": 1,
            #     "run_mode": "pecaan"
            #     }





class TestImportGenomeMain2(unittest.TestCase):
    """Tests involving trying to add a 'final' genome into the database."""


    def setUp(self):
        create_new_db(schema_file, db, user, pwd)
        base_dir.mkdir()
        genome_folder.mkdir()
        output_folder.mkdir()


        # Construct minimal Alice genome
        # CDS 252 is a wrap-around compound gene.
        # CDS 124 is a compound feature.
        # CDS 193 is a normal CDS.
        # CDS 139 is a normal CDS.
        self.alice_cds_252_translation = alice_cds_252_translation
        self.alice_cds_252_qualifier_dict = get_alice_cds_252_qualifier_dict()
        self.alice_cds_252_qualifier_dict["translation"] = \
            [self.alice_cds_252_translation]
        self.alice_cds_252 = get_alice_cds_252_seqfeature()
        self.alice_cds_252.qualifiers = self.alice_cds_252_qualifier_dict

        self.alice_cds_124_translation = alice_cds_124_translation
        self.alice_cds_124_qualifier_dict = get_alice_cds_124_qualifier_dict()
        self.alice_cds_124_qualifier_dict["translation"] = \
            [self.alice_cds_124_translation]
        self.alice_cds_124 = get_alice_cds_124_seqfeature()
        self.alice_cds_124.qualifiers = self.alice_cds_124_qualifier_dict

        self.alice_cds_139_translation = alice_cds_139_translation
        self.alice_cds_139_qualifier_dict = get_alice_cds_139_qualifier_dict()
        self.alice_cds_139_qualifier_dict["translation"] = \
            [self.alice_cds_139_translation]
        self.alice_cds_139 = get_alice_cds_139_seqfeature()
        self.alice_cds_139.qualifiers = self.alice_cds_139_qualifier_dict

        self.alice_cds_193_translation = alice_cds_193_translation
        self.alice_cds_193_qualifier_dict = get_alice_cds_193_qualifier_dict()
        self.alice_cds_193_qualifier_dict["product"] = ["repressor"]

        self.alice_cds_193_qualifier_dict["translation"] = \
            [self.alice_cds_193_translation]
        self.alice_cds_193 = get_alice_cds_193_seqfeature()
        self.alice_cds_193.qualifiers = self.alice_cds_193_qualifier_dict

        self.alice_tmrna_169_qualifier_dict = get_alice_tmrna_169_qualifier_dict()
        self.alice_tmrna_169 = get_alice_tmrna_169()
        self.alice_tmrna_169.qualifiers = self.alice_tmrna_169_qualifier_dict

        self.alice_trna_170_qualifier_dict = get_alice_trna_170_qualifier_dict()
        self.alice_trna_170 = get_alice_trna_170()
        self.alice_trna_170.qualifiers = self.alice_trna_170_qualifier_dict

        self.alice_source_1_qualifiers = get_alice_source_1_qualifiers()
        self.alice_source_1_qualifiers["organism"] = \
            ["Mycobacterium phage Alice"]

        self.alice_source_1 = get_alice_source_1()
        self.alice_source_1.qualifiers = self.alice_source_1_qualifiers

        self.alice_feature_list = [self.alice_source_1,
                                   self.alice_cds_252, # Wrap around gene
                                   self.alice_cds_124, # Compound gene
                                   self.alice_cds_139, # Bottom strand normal CDS
                                   self.alice_tmrna_169,
                                   self.alice_trna_170,
                                   self.alice_cds_193 # Top strand normal CDS
                                   ]

        self.alice_ref1 = Reference()
        self.alice_ref1.authors = author_string_1
        self.alice_ref2 = Reference()
        self.alice_ref2.authors = author_string_2
        self.alice_ref_list = [self.alice_ref1, self.alice_ref2]

        self.alice_description = ("Mycobacterium phage Alice, "
                                  "complete sequence")
        self.alice_organism = "Mycobacterium phage Alice"
        self.alice_source = "Mycobacterium phage Alice"
        self.alice_date = "23-MAR-2018"
        self.alice_accessions = ["JF704092"]
        self.alice_annotation_dict = {
            "accessions": self.alice_accessions,
            "source": self.alice_source,
            "organism": self.alice_organism,
            "references": self.alice_ref_list,
            "date": self.alice_date}
        self.alice_seq = get_seq(base_flat_file_path)
        self.alice_record = SeqRecord(
                                seq = self.alice_seq,
                                id = "JF704092.1",
                                name = "JF704092",
                                annotations = self.alice_annotation_dict,
                                description = self.alice_description,
                                features = self.alice_feature_list
                                )

        # Get data to set up import table.
        self.alice_ticket = get_alice_ticket_data_complete()
        self.alice_ticket["type"] = "replace"
        self.alice_ticket["accession"] = "JF704092"
        self.alice_ticket["annotation_status"] = "final"
        self.alice_ticket["run_mode"] = "phagesdb"

        # Get data to run the entire pipeline.
        self.unparsed_args = get_unparsed_final_import_args()

        # Get data to insert into database that will be replaced.
        self.alice_data_to_insert = get_alice_genome_draft_data_in_db()
        self.alice_data_to_insert["DateLastModified"] = \
            datetime.strptime('1/1/2018', '%m/%d/%Y')


    def tearDown(self):
        shutil.rmtree(base_dir)
        remove_db(db, user, pwd)

        # # This removes the default output folder in the 'tmp'
        # # directory, which gets created if no output folder is
        # # indicated at the command line, which occurs in some tests below.
        # if default_output_path.exists() == True:
        #     shutil.rmtree(default_output_path)









    @patch("getpass.getpass")
    def test_replacement_1(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        valid flat file,
        Alice and non-Alice data already in the database."""
        logging.info("test_replacement_1")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, get_d29_phage_table_data())
        insert_data_into_phage_table(db, user, pwd, get_redrock_phage_table_data())
        insert_data_into_phage_table(db, user, pwd, get_trixie_phage_table_data())
        insert_data_into_gene_table(db, user, pwd, get_trixie_gene_table_data_1())
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        insert_data_into_gene_table(db, user, pwd, get_alice_cds_139_draft_data_in_db())
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        expected_phage_table_data = get_alice_genome_final_data_in_db()
        genome_errors = compare_data(expected_phage_table_data,
                                     output_genome_data)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        process_gene_table_data(gene_table_results)

        cds252_data = filter_gene_data(gene_table_results, alice_cds_252_coords)
        cds124_data = filter_gene_data(gene_table_results, alice_cds_124_coords)
        cds139_data = filter_gene_data(gene_table_results, alice_cds_139_coords)
        cds193_data = filter_gene_data(gene_table_results, alice_cds_193_coords)

        expected_cds252_data = get_alice_cds_252_draft_data_in_db()
        expected_cds124_data = get_alice_cds_124_draft_data_in_db()
        expected_cds139_data = get_alice_cds_139_draft_data_in_db()

        expected_cds193_data = get_alice_cds_193_draft_data_in_db()
        expected_cds193_data["Notes"] = "repressor"

        cds252_errors = compare_data(expected_cds252_data, cds252_data)
        cds124_errors = compare_data(expected_cds124_data, cds124_data)
        cds139_errors = compare_data(expected_cds139_data, cds139_data)
        cds193_errors = compare_data(expected_cds193_data, cds193_data)

        with self.subTest():
            self.assertEqual(len(phage_table_results), 4)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 5)
        with self.subTest():
            self.assertEqual(genome_errors, 0)
        with self.subTest():
            self.assertEqual(cds252_errors, 0)
        with self.subTest():
            self.assertEqual(cds124_errors, 0)
        with self.subTest():
            self.assertEqual(cds139_errors, 0)
        with self.subTest():
            self.assertEqual(cds193_errors, 0)


    @patch("getpass.getpass")
    def test_replacement_2(self, getpass_mock):
        """Test pipeline with:
        valid minimal replace ticket for final genome,
        valid flat file,
        Alice data already in the database."""
        logging.info("test_replacement_2")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        alice_min_tkt = create_min_tkt_dict(self.alice_ticket)
        create_import_table([alice_min_tkt], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        expected_phage_table_data = get_alice_genome_final_data_in_db()
        expected_phage_table_data["Accession"] = ""
        genome_errors = compare_data(expected_phage_table_data,
                                     output_genome_data)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 4)
        with self.subTest():
            self.assertEqual(genome_errors, 0)






    @patch("getpass.getpass")
    def test_replacement_3(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with 'retrieve' or 'retain' fields,
        valid flat file,
        Alice data already in the database."""
        logging.info("test_replacement_3")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        self.alice_ticket["host_genus"] = "RETAIN"
        self.alice_ticket["cluster"] = "RETRIEVE"
        self.alice_ticket["subcluster"] = "RETAIN"
        self.alice_ticket["accession"] = "RETRIEVE"
        self.alice_ticket["retrieve_record"] = "RETAIN"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        expected_phage_table_data = get_alice_genome_final_data_in_db()
        genome_errors = compare_data(expected_phage_table_data,
                                     output_genome_data)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 4)
        with self.subTest():
            self.assertEqual(genome_errors, 0)





    # Run tests using tickets structured incorrectly.

    @patch("pdm_utils.pipelines.db_import.import_genome.process_files_and_tickets")
    @patch("sys.exit")
    @patch("getpass.getpass")
    def test_replacement_4(self, getpass_mock, sys_exit_mock, pft_mock):
        """Test pipeline with:
        invalid replace ticket for final genome,
        with 'retrieve_record' set to 'retrieve', with valid flat file,
        Alice data already in the database."""
        logging.info("test_replacement_4")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        self.alice_ticket["retrieve_record"] = "RETRIEVE"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)
        with self.subTest():
            self.assertTrue(sys_exit_mock.called)



    # Run tests that produce bundle check errors.

    @patch("getpass.getpass")
    def test_replacement_5(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        valid flat file,
        no Alice PhageID data in the database ."""
        logging.info("test_replacement_5")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, get_d29_phage_table_data())

        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")

        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)
        with self.subTest():
            self.assertEqual(len(output_genome_data.keys()), 0)


    @patch("getpass.getpass")
    def test_replacement_6(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome, with some 'retain' fields,
        valid flat file,
        but no Alice PhageID data in the database ."""
        logging.info("test_replacement_6")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, get_d29_phage_table_data())
        self.alice_ticket["host_genus"] = "RETAIN"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)
        with self.subTest():
            self.assertEqual(len(output_genome_data.keys()), 0)




    # Run tests that produce genome_pair check errors.

    @patch("getpass.getpass")
    def test_replacement_7(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        valid flat file,
        Alice PhageID data in the database but incorrect matching data."""
        logging.info("test_replacement_7")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        d29_phage_table_data = get_d29_phage_table_data()
        d29_phage_table_data["PhageID"] = "Alice"
        insert_data_into_phage_table(db, user, pwd, d29_phage_table_data)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        genome_errors = compare_data(d29_phage_table_data, output_genome_data)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)
        with self.subTest():
            self.assertEqual(genome_errors, 0)
        with self.subTest():
            self.assertFalse(alice_flat_file_path.exists())
        with self.subTest():
            self.assertFalse(success_path.exists())
        with self.subTest():
            self.assertTrue(fail_alice_path.exists())
        with self.subTest():
            self.assertTrue(fail_table_path.exists())


    @patch("getpass.getpass")
    def test_replacement_8(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        valid flat file,
        Alice PhageID data in the database but genome sequences don't match."""
        logging.info("test_replacement_8")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        alice_seq_mod = str(get_seq(base_flat_file_path))
        alice_seq_mod = list(alice_seq_mod)
        alice_seq_mod[100] = "-"
        alice_seq_mod = "".join(alice_seq_mod)
        alice_seq_mod = Seq(alice_seq_mod, IUPAC.ambiguous_dna)
        exp_phage_table_data = get_alice_genome_final_data_in_db()
        exp_phage_table_data["Sequence"] = alice_seq_mod
        insert_data_into_phage_table(db, user, pwd, exp_phage_table_data)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        genome_errors = compare_data(exp_phage_table_data, output_genome_data)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)
        with self.subTest():
            self.assertEqual(genome_errors, 0)
        with self.subTest():
            self.assertFalse(alice_flat_file_path.exists())
        with self.subTest():
            self.assertFalse(success_path.exists())
        with self.subTest():
            self.assertTrue(fail_alice_path.exists())
        with self.subTest():
            self.assertTrue(fail_table_path.exists())


    @patch("getpass.getpass")
    def test_replacement_9(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        valid flat file,
        but Alice data in the database is not older than new genome."""
        logging.info("test_replacement_9")
        getpass_mock.side_effect = [user, pwd]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        self.alice_data_to_insert["DateLastModified"] = \
            datetime.strptime('1/1/4018', '%m/%d/%Y')
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)
        with self.subTest():
            self.assertEqual(output_genome_data["DateLastModified"],
                             self.alice_data_to_insert["DateLastModified"])



    # TODO genome_pair check - insert test to verify error when PhageID still has _Draft suffix.
    # TODO genome_pair check - check 'draft' to 'gbk' error


    # TODO genome_pair check - check 'final' to 'final' no error
    # TODO genome_pair check - check 'final' to 'gbk' error







    # Run tests that produce genome check errors.

    @patch("getpass.getpass")
    def test_replacement_10(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        but flat file with no CDS descriptions in product field."""
        logging.info("test_replacement_10")
        getpass_mock.side_effect = [user, pwd]
        clear_descriptions(self.alice_record)
        self.alice_record.features[1].qualifiers["function"] = "repressor"
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)
        with self.subTest():
            self.assertEqual(output_genome_data["DateLastModified"],
                             self.alice_data_to_insert["DateLastModified"])


    @patch("getpass.getpass")
    def test_replacement_11(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with 'description_field' = 'function',
        and flat file with CDS descriptions in function field."""
        logging.info("test_replacement_11")
        getpass_mock.side_effect = [user, pwd]
        clear_descriptions(self.alice_record)
        self.alice_record.features[1].qualifiers["function"] = "repressor"
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        self.alice_ticket["description_field"] = "function"
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        process_phage_table_data(phage_table_results)
        output_genome_data = filter_genome_data(phage_table_results, "Alice")
        exp_phage_table_data = get_alice_genome_final_data_in_db()
        genome_errors = compare_data(exp_phage_table_data, output_genome_data)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 4)
        with self.subTest():
            self.assertEqual(genome_errors, 0)


    @patch("getpass.getpass")
    def test_replacement_12(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        and flat file has phage_id typo in source field."""
        logging.info("test_replacement_12")
        getpass_mock.side_effect = [user, pwd]
        self.alice_record.annotations["source"] = "Mycobacterium phage D29"
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_replacement_13(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        and flat file has host_genus typo in source field."""
        logging.info("test_replacement_13")
        getpass_mock.side_effect = [user, pwd]
        self.alice_record.annotations["source"] = "Gordonia phage Alice"
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_replacement_14(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome,
        and flat file has missing author in authors list."""
        logging.info("test_replacement_14")
        getpass_mock.side_effect = [user, pwd]
        self.alice_ref2.authors = ("Alferez,G.I., Bryan,W.J., "
                                   "Byington,E.L., Contreras,T.D.")
        self.alice_record.annotations["references"] = [self.alice_ref2]
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)





    # Run tests that produce Source check errors.

    @patch("getpass.getpass")
    def test_replacement_15(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with
        id typo in source feature."""
        logging.info("test_replacement_15")
        getpass_mock.side_effect = [user, pwd]
        mod_organism = ["Mycobacterium phage Alice_Draft"]
        self.alice_record.features[0].qualifiers["organism"] = mod_organism
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_replacement_16(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with
        host_genus typo in source feature."""
        logging.info("test_replacement_16")
        getpass_mock.side_effect = [user, pwd]
        mod_organism = ["Mycobacteriu phage Alice"]
        self.alice_record.features[0].qualifiers["organism"] = mod_organism
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_replacement_17(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with
        host_genus variant spelling in source feature organism field."""
        logging.info("test_replacement_17")
        getpass_mock.side_effect = [user, pwd]
        mod_organism = ["Mycobacteriophage Alice"]
        self.alice_record.features[0].qualifiers["organism"] = mod_organism
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 4)


    @patch("getpass.getpass")
    def test_replacement_18(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with
        host_genus variant spelling in source feature host field."""
        logging.info("test_replacement_18")
        getpass_mock.side_effect = [user, pwd]
        mod_organism = ["Mycobacteriophage Alice"]
        self.alice_record.features[0].qualifiers["host"] = mod_organism
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)



    # Run tests that produce CDS check errors.


    @patch("getpass.getpass")
    def test_replacement_19(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with
        CDS feature with incorrect phage name in locus_tag."""
        logging.info("test_replacement_19")
        getpass_mock.side_effect = [user, pwd]
        self.alice_record.features[1].qualifiers["locus_tag"] = "L5_1"
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_replacement_20(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with
        CDS feature with incorrect gene qualifier structure."""
        logging.info("test_replacement_20")
        getpass_mock.side_effect = [user, pwd]
        self.alice_record.features[1].qualifiers["gene"] = "invalid"
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)


    @patch("getpass.getpass")
    def test_replacement_21(self, getpass_mock):
        """Test pipeline with:
        valid replace ticket for final genome with
        CDS feature with containing description in 'function'
        even though description_field = 'product'. (One CDS feature contains
        valid description in product though, so the genome-level
        check for number of descriptions > 1 does not generate an error)."""
        logging.info("test_replacement_21")
        getpass_mock.side_effect = [user, pwd]
        clear_descriptions(self.alice_record)
        self.alice_record.features[1].qualifiers["product"] = "int"
        self.alice_record.features[2].qualifiers["function"] = "repressor"
        SeqIO.write(self.alice_record, alice_flat_file_path, "genbank")
        insert_data_into_phage_table(db, user, pwd, self.alice_data_to_insert)
        create_import_table([self.alice_ticket], import_table)
        run.main(self.unparsed_args)
        phage_table_results = get_sql_data(db, user, pwd, phage_table_query)
        gene_table_results = get_sql_data(db, user, pwd, gene_table_query)
        with self.subTest():
            self.assertEqual(len(phage_table_results), 1)
        with self.subTest():
            self.assertEqual(len(gene_table_results), 0)






        # Tests performed on 'final' genome:
        #2. replace Alice data
        #1. fail trying to replace Alice genome when sequences don't match.
        #3. fail trying to replace Alice genome when there is no matching PhageID.
        #3. use invalid ticket
        #4. use minimal ticket.
        #13. set some ticket fields to 'retain', but have PhageID that is not found in Phamerator.
        #14. Date that is not newer.
        #12. test description_field = function instead of product
        #12 check id_typo in organism field
        #12 check host_genus in organism field
        #6. fail due to genome-level error
        #10. fail due to source error.
        #7. fail due to CDS error.



        # Tests to perform on Alice 'final' genome:
        #7. fail due to genome-pair error.
        #11. test interactivity
        #12. verify that CDS features are completely replaced - test by inserting diff data at the beginning.
        #13. verify locus_tags are not imported!



        # Tests using 'add' ticket:
        # 1. set some ticket fields to 'retrieve', but have PhageID that is not found on PhagesDB.



        # Other tests:
        #1. how multiple successful tickets and genomes are handled.
        #2. how a failed and successful ticket are handled.
        #3. different run_modes in ticket and/or from command line are handled.



        # dict = {
        #     "id": 1,
        #     "type": "add",
        #     "phage_id": "Alice",
        #     "host_genus": "Mycobacterium",
        #     "cluster": "C",
        #     "subcluster": "C1",
        #     "accession": "none",
        #     "description_field": "product",
        #     "annotation_status": "draft",
        #     "annotation_author": 1,
        #     "retrieve_record": 1,
        #     "run_mode": "pecaan",
        #     }



        # for cdsftr in gene_table_results:
        #     print(cdsftr["GeneID"])
        #     print(cdsftr["Start"])
        #     print(cdsftr["Stop"])


        # input("check log")

        # results = get_sql_data(db, user, pwd, phage_table_query)
        # print(len(results))
        # results2 = get_sql_data(db, user, pwd, gene_table_query)
        # print(len(results2))
        # input("paused")
        # seq = get_seq(self.test_flat_file1)
        # l5_phage_table_data["sequence"] = seq
        # l5_phage_table_data["SequenceLength"] = len(seq)
        # print(l5_phage_table_data["sequence"][:25])
        # print(l5_phage_table_data["SequenceLength"])
        # input("pause")
        # insert_data_into_phage_table(db, user, pwd, l5_phage_table_data)
        # input("pause2")
        # keys = set(["host_genus", "cluster", "subcluster"])
        # l5_ticket_data_retrieve = set_data(get_l5_ticket_data_complete(), keys, "retrieve")

        # shutil.copy(self.base_flat_file_path, self.genome_folder)


if __name__ == '__main__':
    unittest.main()
