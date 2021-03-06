Library tutorial
================

``pdm_utils`` provides a library of functions, classes, and methods that can be used to develop customized data analysis pipelines. Below is a brief introduction to how the library can be used.

In the shell terminal, activate the Conda environment containing the installed
``pdm_utils`` package (if needed) to ensure all dependencies are present. Then open a Python IDE::

    > conda activate pdm_utils
    (pdm_utils)>
    (pdm_utils)> python3
    >>>



Connect to the MySQL database
*****************************

In order to retrieve and explore data stored within the MySQL database, create a SQLAlchemy 'engine'. This object provides the core interface between Python and MySQL. It stores information about the database of interest, login credentials and connection status so that they do not need to be provided multiple times, and it contains methods to directly interact with the database. The ``pdm_utils`` 'mysqldb' module provides several functions that rely on the engine. To start, create an engine to the primary database, and provide the username and password when prompted::

    >>> from pdm_utils.functions import mysqldb
    >>> engine = mysqldb.connect_to_db(database='Actinobacteriophage')
    MySQL username:
    MySQL password:

MySQL queries can be executed using the engine. In the following example, a list of 90 phages in Subcluster A2 are retrieved. For each phage, a dictionary of data is returned::

    >>> result = engine.execute("SELECT PhageID,HostGenus FROM phage WHERE Subcluster = 'A2'")
    >>> phages = result.fetchall()
    >>> len(phages)
    90
    >>> dict(phages[0])
    {'PhageID': '20ES', 'HostGenus': 'Mycobacterium'}

MySQL transactions can also be executed using the engine. It returns 0 if successful, or 1 if unsuccessful::

    >>> txn_result = mysqldb.execute_transaction(engine, ["UPDATE phage SET HostGenus = 'Arthrobacter' WHERE PhageID = '20ES'"])
    >>> txn_result
    0
    >>> result = engine.execute("SELECT PhageID,HostGenus FROM phage WHERE Subcluster = 'A2'")
    >>> phages = result.fetchall()
    >>> dict(phages[0])
    {'PhageID': '20ES', 'HostGenus': 'Arthrobacter'}



Access ``pdm_utils`` Genome data
********************************

Data can also be retrieved in an object-oriented structure. First, create a list of phages for which data should be retrieved. These are expected to be stored in the PhageID column of the *phage* table::

    >>> phage_id_list = ['L5', 'Trixie', 'D29']

Construct the MySQL query to retrieve the specific types of data from the *phage* table and the *gene* table::

    >>> phage_query = 'SELECT PhageID, Name, Sequence, Cluster, Subcluster, Status, HostGenus FROM phage'
    >>> gene_query = 'SELECT GeneID, Start, Stop, Orientation, Translation, Notes FROM gene'

The parse_genome_data function retrieves the data and constructs ``pdm_utils`` Genome and Cds objects from the data. In the example below, there are three Genome objects created, each corresponding to a different phage in phage_id_list::

    >>> phage_data = mysqldb.parse_genome_data(engine, phage_id_list=phage_id_list, phage_query=phage_query, gene_query=gene_query)
    >>> len(phage_data)
    3


Data for each phage can be directly accessed::

    >>> phage_data[0].id
    'D29'
    >>> d29 = phage_data[0]
    >>> d29.host_genus
    'Mycobacterium'
    >>> d29.cluster
    'A'
    >>> d29.subcluster
    'A2'
    >>> d29.annotation_status
    'final'

The genome sequence is stored in the seq attribute as a Biopython Seq object,
so Biopython Seq attributes and methods (such as 'lower' or 'reverse_complement') can also be directly accessed::

    >>> len(d29.seq)
    49136
    >>> d29.seq[:10]
    Seq('GGTCGGTTAT')
    >>> d29.seq[:10].lower()
    Seq('ggtcggttat')
    >>> d29.seq[:10].reverse_complement()
    Seq('ATAACCGACC')



Access ``pdm_utils`` Cds data
*****************************

Data from the *gene* table is retrieved and parsed into Cds objects.
For each phage, all Cds objects for are stored in the Genome object's 'cds_features' attribute as a list. Data for each CDS feature can be directly accessed::

    >>> len(d29.cds_features)
    77
    >>> cds54 = d29.cds_features[54]
    >>> cds54.description
    'DNA primase'
    >>> cds54.start
    38737
    >>> cds54.stop
    39127
    >>> cds54.orientation
    'R'
    >>> cds54.coordinate_format
    '0_half_open'


Similar to the nucleotide sequence in the Genome object, the CDS translation is stored in the translation attribute as a Biopython Seq object::

    >>> cds54.translation
    Seq('MTATGIAEVIQRYYPDWDPPPDHYEWNKCLCPFHGDETPSAAVSYDLQGFNCLA...PWS', IUPACProtein())


The nucleotide sequence for each Cds feature is not explicitly stored in the MySQL database. The sequence can be extracted from the parent genome, but this relies on the Cds object containing a Biopython SeqFeature object stored in the seqfeature attribute, but this is also empty at first::

    >>> cds54.seq
    Seq('', IUPACAmbiguousDNA())
    >>> cds54.seqfeature



To extract the sequence, first construct the Biopython SeqFeature object::

    >>> cds54.set_seqfeature()
    >>> cds54.seqfeature
    SeqFeature(FeatureLocation(ExactPosition(38737), ExactPosition(39127), strand=-1), type='CDS')

With the SeqFeature constructed, the 390 bp nucleotide sequence can be retrieved from the parent genome::

    >>> cds54.set_nucleotide_sequence(parent_genome_seq=d29.seq)
    >>> cds54.seq
    Seq('TTGACAGCCACCGGCATCGCGGAGGTCATCCAGCGGTACTACCCGGACTGGGAT...TGA')
    >>> len(cds54.seq)
    390


.. Note: commented out until filter module is revamped.
.. Access subsets of data using a ``pdm_utils`` Filter
.. ***************************************************
..
..
.. Sometimes data pertaining to a large set of phages (for instance, all Subcluster A2 phages) is needed. Manually constructing the list of PhageIDs is time intensive and error prone, but can be automatically generated using a ``pdm_utils`` Filter object. Import the filter module, and create a Filter object using the engine::
..
..     >>> from pdm_utils.classes import filter
..     >>> db_filter = filter.Filter(engine)
..
.. Creating the Subcluster filter identifies 90 phages in Subcluster A2::
..
..     >>> db_filter.add_filter(raw_table="phage", raw_field="Subcluster", value="A2", verbose=True)
..     >>> db_filter.refresh()
..     >>> db_filter.update(verbose=True)
..     Filtering phage in Actinobacteriophage for Subcluster='A2'...
..     >>> db_filter.hits(verbose=True)
..     Database hits: 90
..
.. The filter results are stored in the values attribute, and can be sorted and accessed::
..
..     >>> db_filter.sort(sort_field="PhageID", verbose=True)
..     Sorting by 'PhageID'...
..     >>> len(db_filter.values)
..     90
..     >>> db_filter.values[:10]
..     ['20ES', 'AbbyPaige', 'Acolyte', 'Adzzy', 'AN3', 'AN9', 'ANI8', 'AnnaL29', 'Anselm', 'ArcherNM']
..
..
.. This list of PhageIDs can now be passed to other functions, such as mysqldb.parse_genome_data(). The filtered results can be filtered further if needed. Suppose that only Subcluster A2 phages that contain at least
.. one gene that is annotated as the 'repressor' are needed. This filter can be added, resulting in a list of only 4 phages::
..
..     >>> db_filter.add_filter(table="gene", raw_field="Notes",value="repressor", verbose=True)
..     >>> db_filter.refresh()
..     >>> db_filter.update(verbose=True)
..     >>> db_filter.hits(verbose=True)
..     Database hits: 4
..     4
..     >>> db_filter.values
..     ['Pukovnik', 'RedRock', 'Odin', 'Adzzy']
..
..
.. When all interaction with MySQL is complete, the DBAPI connections can be closed::
..
..     >>> engine.dispose()
..
.. For more information on how different Genome and Cds object attributes map to the MySQL database, refer to the :ref:`object attribute maps <attributemap>`.
