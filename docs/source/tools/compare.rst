.. _compare:

compare: compare data between databases
=======================================

In the SEA-PHAGES program, genomics data may be stored in three separate databases (a local MySQL database, PhagesDB, and GenBank). As a result, data inconsistencies may arise without a mechanism to compare and synchronize different data sources. Although the import tool implements many QC checks for this purpose, it only ensures consistency for the specific genomes being imported and it only cross-checks databases as directed by the import ticket. In order to ensure comprehensive consistency, the ``pdm_utils compare`` tool can perform an all-against-all data assessment::

    > python3 -m pdm_utils compare Actinobacteriophage ./


The argument 'Actinobacteriophage' indicates the name of the local MySQL database that serves as the central data source for the comparison. The './' argument indicates the directory in which the results are stored.

Data in a MySQL database can be compared to either PhagesDB data or GenBank data, or data can be compared between all three databases (it does not compare PhagesDB data to GenBank data unless it also compares MySQL database data). All phage data, or subsets of phage data, can be compared. For instance, the administrator can compare genomes depending on their annotation status (draft, final, or unknown) or their authorship (hatfull, non-hatfull).

The ``compare`` tool retrieves data stored in the *phage* and *gene* tables. PhagesDB data for all sequenced phages are retrieved from: http://phagesdb.org/api/sequenced_phages/. All GenBank records are retrieved using accession numbers stored in the Accession field of the *phage* table. All data is matched between the local MySQL database and PhagesDB using the PhageID field in the *phage* and the phage name in PhagesDB. All data is matched between the local MySQL database and GenBank using the Accession field in the *phage* table. After retrieving and matching data from all databases, the script compares the genome data (e.g. phage name, host strain, genome sequence, etc.) and gene data (e.g. locus tags, coordinates, descriptions, etc.), and generates several results files. Additionally, the script can output genomes retrieved from all three databases for future reference and analysis if selected by the user.
