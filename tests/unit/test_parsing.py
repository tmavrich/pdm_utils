from pdm_utils.functions import parsing
from sqlalchemy import Column
from sqlalchemy import MetaData
from sqlalchemy import Table
from unittest.mock import Mock, patch, PropertyMock
import unittest
import re

class TestParsing(unittest.TestCase):
    def test_parse_out_ends_1(self):
        string = "Trixie"

        trimmed_string = parsing.parse_out_ends(string)

        self.assertEqual(string, trimmed_string)

    def test_parse_out_ends_2(self):
        string = " Trixie"

        trimmed_string = parsing.parse_out_ends(string)

        self.assertEqual("Trixie", trimmed_string)

    def test_parse_out_ends_3(self):
        string = " Trixie "

        trimmed_string = parsing.parse_out_ends(string)
        
        self.assertEqual("Trixie", trimmed_string)

    def test_parse_out_ends_4(self):
        with self.assertRaises(TypeError):
            parsing.parse_out_ends(["Fail"])

    def test_parse_in_ends_1(self):
        with self.assertRaises(TypeError):
            parsing.parse_in_ends("Not a list")

    def test_parse_in_ends_2(self):
        expected_string = "Example of final joined string"

        string_list = ["Example", "of", "final", "joined", "string"]
        final_string = parsing.parse_in_ends(string_list)

        self.assertEqual(expected_string, final_string)

    def test_parse_cmd_string_1(self):
        filters_string = "phage.PhageID=Trixie AND gene.Notes=Antirepressor"
        
        parsed_string = parsing.parse_cmd_string(filters_string)

        self.assertTrue(len(parsed_string) == 2)
        self.assertEqual(parsed_string[0], ["phage.PhageID=Trixie"])
        self.assertEqual(parsed_string[1], ["gene.Notes=Antirepressor"])

    def test_parse_cmd_string_2(self):
        filters_string = ("phage.PhageID = Trixie OR "
                          "gene.Notes  = Antirepressor")

        parsed_string = parsing.parse_cmd_string(filters_string)

        self.assertTrue(len(parsed_string) == 1)
        self.assertTrue(len(parsed_string[0]) == 2)
        self.assertEqual(parsed_string[0][0], "phage.PhageID = Trixie")
        self.assertEqual(parsed_string[0][1], "gene.Notes  = Antirepressor")

    def test_parse_cmd_string_3(self):
        filters_string = ("phage.PhageID LIKE Trixie OR "
                          "gene.Notes IS NOT Antirepressor")
 
        parsed_string = parsing.parse_cmd_string(filters_string)

        self.assertTrue(len(parsed_string) == 1)
        self.assertTrue(len(parsed_string[0]) == 2)
        self.assertEqual(parsed_string[0][0], "phage.PhageID LIKE Trixie")
        self.assertEqual(parsed_string[0][1], "gene.Notes IS NOT Antirepressor")

    def test_parse_cmd_string_4(self):
        filters_string = ("phage.PhageID LIKE Trixie OR "
                          "gene.Notes IS NOT Antirepressor")
 
        parsed_string = parsing.parse_cmd_string(filters_string)

        self.assertTrue(len(parsed_string) == 1)
        self.assertTrue(len(parsed_string[0]) == 2)
        self.assertEqual(parsed_string[0][0], "phage.PhageID LIKE Trixie")
        self.assertEqual(parsed_string[0][1], "gene.Notes IS NOT Antirepressor")

    def test_parse_cmd_string_5(self):
        filters_string = ("phage.PhageID LIKE Trixie OR")
        
        with self.assertRaises(ValueError):
            parsed_cmd_line = parsing.parse_cmd_string(filters_string)

    def test_parse_cmd_filter_5(self):
        filters_string = ("phage.PhageID LIKE Trixie")

        parsed_filters = parsing.parse_cmd_string(filters_string)
  
    @patch("pdm_utils.functions.parsing.parse_in_ends")
    def test_parse_cmd_list_1(self, ParseInEnds):
        ParseInEnds.return_value = ("phage.PhageID LIKE Trixie OR "
                                    "gene.Notes LIKE Antirepressor")

        unparsed_string_list = ["Example", "unparsed", "string", "list"]
        parsing.parse_cmd_list(unparsed_string_list)

        ParseInEnds.assert_called_with(unparsed_string_list)

    @patch("pdm_utils.functions.parsing.parse_cmd_string") 
    def test_parse_cmd_list_2(self, ParseCmdString):
        expected_parsed_string = ("phage.PhageID LIKE Trixie OR "
                                  "gene.Notes LIKE Antirepressor")

        unparsed_string_list = ["phage.PhageID", "LIKE", "Trixie", "OR",
                                "gene.Notes", "LIKE", "Antirepressor"]

        parsing.parse_cmd_list(unparsed_string_list)

        ParseCmdString.assert_called_with(expected_parsed_string)


    def test_parse_column_1(self):
        column_string = "phage.PhageID"

        parsed_column = parsing.parse_column(column_string)
        
        self.assertEqual(parsed_column[0], "phage")
        self.assertEqual(parsed_column[1], "PhageID")

    def test_parse_column_2(self):
        column_string = " phage.PhageID "

        parsed_column = parsing.parse_column(column_string)
        
        self.assertEqual(parsed_column[0], "phage")
        self.assertEqual(parsed_column[1], "PhageID")

    def test_parse_column_3(self):
        column_string = "phage. PhageID"

        with self.assertRaises(ValueError):
            parsed_column = parsing.parse_column(column_string)
        
    def test_parse_filter_1(self):
        filter = "phage.PhageID=Trixie"

        parsed_filter = parsing.parse_filter(filter)

        self.assertTrue(len(parsed_filter) == 4)
        self.assertEqual(parsed_filter[0], "phage")
        self.assertEqual(parsed_filter[1], "PhageID")
        self.assertEqual(parsed_filter[2], "=")
        self.assertEqual(parsed_filter[3], "Trixie")

    def test_parse_filter_2(self):
        filter = "phage.PhageID = Trixie"

        parsed_filter = parsing.parse_filter(filter)

        self.assertTrue(len(parsed_filter) == 4)
        self.assertEqual(parsed_filter[0], "phage")
        self.assertEqual(parsed_filter[1], "PhageID")
        self.assertEqual(parsed_filter[2], "=")
        self.assertEqual(parsed_filter[3], "Trixie")

    def test_parse_filter_3(self):
        filter = "phage. PhageID = Trixie"

        with self.assertRaises(ValueError):
            parsed_filter = parsing.parse_filter(filter)

    def test_parse_filter3(self):
        filter = "phage.PhageID Trixie = "

        with self.assertRaises(ValueError):
            parsed_filter = parsing.parse_filter(filter)

class TestCheckOperator(unittest.TestCase):
    def setUp(self):
        self.str_column = Mock(spec=Column)
        self.num_column = Mock(spec=Column)
        self.bool_column = Mock(spec=Column)

        type(self.str_column).name  = PropertyMock(return_value="str_column")
        type(self.num_column).name  = PropertyMock(return_value="num_column")
        type(self.bool_column).name = PropertyMock(return_value="bool_column")

        self.str_column_type  = Mock()
        self.num_column_type  = Mock()
        self.bool_column_type = Mock()

        type(self.str_column).type  = self.str_column_type
        type(self.num_column).type  = self.num_column_type
        type(self.bool_column).type = self.bool_column_type

        type(self.str_column_type).python_type = PropertyMock(return_value=str)
        type(self.num_column_type).python_type = PropertyMock(return_value=int)
        type(self.bool_column_type).python_type = \
                                                 PropertyMock(return_value=bool)



    def test_check_operator_1(self):
        with self.assertRaises(ValueError):
            parsing.check_operator("#", self.str_column) 
            
    def test_check_operator_2(self):
        with self.assertRaises(ValueError):
            parsing.check_operator("=", self.bool_column)

    def test_check_operator_3(self):
        for operator in parsing.OPERATORS:
            with self.subTest(operator=operator):
                parsing.check_operator(operator, self.num_column)

    def test_check_operator_4(self):
        for operator in parsing.COMPARATIVE_OPERATORS:
            with self.subTest(comparative_operator=operator):
                with self.assertRaises(ValueError):
                    parsing.check_operator(operator, self.str_column)

    def test_check_operator_5(self):
        with self.assertRaises(TypeError):
            parsing.check_operator("=", Mock())

class TestTranslate(unittest.TestCase):
    def setUp(self):
        self.metadata = Mock(spec=MetaData)

        self.phage = Mock(spec=Table)
        self.gene  = Mock(spec=Table)
        self.trna  = Mock(spec=Table)

        type(self.phage).name = PropertyMock("phage")
        type(self.gene).name  = PropertyMock("gene")
        type(self.trna).name  = PropertyMock("trna")

        self.table_inputs = ["pHaGe", "GenE", "tRNA"]
        
        self.tables = ["phage", "gene", "trna"]

        tables = {"phage" : self.phage,
                  "gene"  : self.gene,
                  "trna"  : self.trna}

        type(self.metadata).tables = PropertyMock(return_value=tables)

        self.column_inputs = ["pHaGe.phageiD",
                              "GenE.GeNEid",
                              "tRNA.notes"]

        self.columns = ["PhageID", "GeneID", "Notes"]

        self.PhageID = Mock(spec=Column)
        self.GeneID = Mock(spec=Column)
        self.Notes = Mock(spec=Column)

        type(self.phage).columns = PropertyMock(
                                    return_value={"PhageID" : self.PhageID})
        type(self.gene).columns  = PropertyMock(
                                    return_value={"GeneID" : self.GeneID})
        type(self.trna).columns  = PropertyMock(
                                    return_value={"Notes" : self.Notes})
    
    def test_translate_table_1(self):
        for table in self.table_inputs:
            with self.subTest(table_input=table):
                translated = parsing.translate_table(self.metadata, table)
                self.assertTrue(translated in self.tables)

    def test_translate_table_2(self):
        with self.assertRaises(ValueError):
            parsing.translate_table(self.metadata, "pham")

    def test_translate_table_1(self):
        for column in self.column_inputs:
            with self.subTest(column_input=column):
                translated = parsing.translate_column(self.metadata, column)

    def test_translate_table_2(self):
        with self.assertRaises(ValueError):
            parsing.translate_column(self.metadata, "phage.Cluster")

if __name__ == "__main__":
    unittest.main()

