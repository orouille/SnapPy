from __future__ import print_function
# NB: this module uses the Manifold class from snappy, and the
# snappy.Manifold class uses objects from this module in its __init__
# method.  This works because we only call snappy.Manifold('empty')
# here.  It will not work to use "from snappy import Manifold".
import snappy
from snappy.db_utilities import decode_torsion, decode_matrices, db_hash
from spherogram.codecs import DTcodec
import sqlite3, re, os, random

try:
    unicode
    byte_to_int = ord
except NameError: # Python 3
    byte_to_int = int

try:
    import sage.all
    def is_int(slice):
        return isinstance(slice, (sage.all.Integer,int))
        
    def is_int_or_none(slice):
        return isinstance(slice, (sage.all.Integer,int, type(None)))

    def is_float_or_none(slice):
        return isinstance(slice, (float, sage.all.RealDoubleElement,
                                  sage.rings.real_mpfr.RealNumber, type(None)))

except ImportError:
    def is_int(slice):
        return isinstance(slice, int)
    
    def is_int_or_none(slice):
        return isinstance(slice, (int, type(None)))

    def is_float_or_none(slice):
        return isinstance(slice, (float, type(None)))

# This module uses sqlite3 databases with multiple tables.
# The path to the database file is specified at the module level.
from snappy.manifolds import __path__ as manifolds_paths
manifolds_path = manifolds_paths[0]
database_path = os.path.join(manifolds_path, 'manifolds.sqlite')
# Temporary - should get this from preferences.
alt_database_path = os.path.join(manifolds_path, 'more_manifolds.sqlite')

USE_COBS = 1 << 7
USE_STRING = 1 << 6
CUSP_MASK = 0x3f

class ManifoldTable(object):
    """
    Iterator for cusped manifolds in an sqlite3 table of manifolds.

    Initialize with the table name.  The table schema is required to
    include a text field called 'name' and a blob field called
    'triangulation'.  The blob holds the result of M._to_bytes() or
    M._to_string(), optionally preceded by a change of basis matrix
    for the peripheral curves.  The structure of the blob is
    determined by its first byte.

    Both mapping from the manifold name, and lookup by index are
    supported.  Slicing can be done either by numerical index or by
    volume.

    The __contains__ method is supported, so M in T returns True if M
    is isometric to a manifold in the table T.  The method
    T.identify(M) will return the matching manifold from the table.
    """
    # basic select clause.  Can be overridden, e.g. to additional columns
    _select = 'select name, triangulation, perm from %s '

    def __init__(self, table='', db_path=database_path,
                 mfld_hash=db_hash, **filter_args):
        self._table = table
        self.mfld_hash = mfld_hash
        self._connection = sqlite3.connect(db_path)
        self._connection.row_factory = self._manifold_factory
        # Sometimes we need a connection without the row factory
        self._connection2 = conn = sqlite3.connect(db_path)
        cursor = conn.execute("pragma table_info('%s')"%table)
        rows = cursor.fetchall()
        self.schema = dict([(row[1],row[2].lower()) for row in rows])
        assert self.schema['name'] == 'text' and \
               self.schema['triangulation'] == 'blob', \
               'Not a valid Manifold table.'
        cursor = conn.execute("select count(*) from %s"%self._table)
        self._configure(**filter_args)
        self._get_length()
        self._select = self._select%table

    @property
    def filter(self):
        return self._filter

    def _get_length(self):
        where_clause = 'where ' + self._filter if self._filter else '' 
        length_query = 'select count(*) from %s %s' % (self._table,
                                                       where_clause)
        cursor = self._connection2.execute(length_query)
        self._length = cursor.fetchone()[0]
        
    def _configure(self, **kwargs):
        """
        Set up the filter.
        """
        conditions = []

        if 'filter' in kwargs:
            conditions.append(kwargs['filter'])
        if 'betti' in kwargs:
            conditions.append('betti=%d ' % kwargs['betti'])
        if 'num_cusps' in kwargs:
            conditions.append('cusps=%d ' % kwargs['num_cusps'])
        if 'cusps' in kwargs:
            conditions.append('cusps=%d ' % kwargs['cusps'])
        if 'num_tets' in kwargs:
            conditions.append('tets=%d ' % kwargs['num_tets'])
        if 'tets' in kwargs:
            conditions.append('tets=%d ' % kwargs['tets'])
        self._filter = ' and '.join(conditions)
         
    def __repr__(self):
        class_name = self.__class__.__name__
        if self._filter == '':
            return '%s without filters'%class_name
        else:
            return '%s with filter: %s'%(class_name, self._filter)
        
    def __call__(self, **kwargs):
        return self.__class__(**kwargs)
    
    def __len__(self):
        return self._length
        
    def __iter__(self):
        query = self._select
        if self._filter:
            query += ' where %s '%self._filter
        return self._connection.execute(query)

    def __contains__(self, mfld):
        try:
            M = self.identify(mfld)
            # duck test
            return M.num_tetrahedra() > 0
        except:
            return False
        
    def __getitem__(self, index):
        if isinstance(index, slice):
            if index.step:
                raise IndexError('Slices with steps are not supported.')
            start, stop = index.start, index.stop
            if is_float_or_none(start) and is_float_or_none(stop):
                # Slice by volume.
                conditions = []
                if self._filter:
                    conditions.append(self._filter)
                if start:
                    conditions.append('volume >= %f' % start)
                if stop:
                    conditions.append('volume < %f' % stop)
                where_clause = ' and '.join(conditions)
                if where_clause:
                    where_clause = 'where ' + where_clause
                query = (self._select + where_clause)
                return self._connection.execute(query).fetchall()
            elif (is_int_or_none(start) and is_int_or_none(stop)):
                if start and start < 0:
                    start = int(self._length + start)
                if stop and stop < 0:
                    stop = int(self._length + stop)
                if self._filter == '':
                    # With no filter we can slice by the id field;
                    start = 0 if start is None else start 
                    limit_clause = ' limit %d '%(stop - start) if stop else ''
                    query = (self._select + 'where id >= %d  %s ' % (
                                 start + 1,
                                 limit_clause))
                    return self._connection.execute(query)
                # otherwise we just trash the rows at the beginning. :^(
                else:
                    limit_clause = ' limit %d'%stop if stop else ''
                    query = (self._select + 'where %s %s'%(
                                 self._filter, limit_clause))
                    cursor = self._connection.execute(query)
                    if start:
                        cursor.row_factory = lambda x, y : None
                        cursor.fetchmany(start)
                        cursor.row_factory = self._manifold_factory
                    return cursor
            else:
                raise IndexError(
                    'Use two ints or two floats for start and stop.')
        elif is_int(index):
            matches = self.find('id=%d'%(index + 1))
            if len(matches) != 1:
                raise IndexError('Manifold index is out of bounds')
        elif isinstance(index, str):
            matches = self.find("name='%s'"%index)
            if len(matches) != 1:
                raise KeyError('The manifold %s was not found.'%index)
        else:
            raise IndexError('%s is not a valid index type for manifolds.'%
                             type(index))
        return matches[0]
    
    def _manifold_factory(self, cursor, row):
        """
        Factory for "select name, triangulation" queries.
        Returns a Manifold.
        """
        buf = bytes(row[1])
        header = byte_to_int(buf[0])
        use_cobs, use_string = header&USE_COBS, header&USE_STRING
        num_cusps = header&CUSP_MASK
        M = snappy.Manifold('empty')
        if use_string:
            M._from_string(buf[1:])
        else:
            M._from_bytes(buf[4*num_cusps + 1:])
            if use_cobs:
                cobs = decode_matrices(buf[1:4*num_cusps + 1])
                M.set_peripheral_curves('combinatorial')
                M.set_peripheral_curves(cobs)
        self._finalize(M, row)
        return M

    def _finalize(self, M, row):
        """
        Give the manifold a name and make last-minute adjustments
        to the manifold before it leaves the factory, e.g. Dehn filling.
        Override this method for custom manifold production.
        """
        M.set_name(row[0])
        num = M.num_cusps()
        encoded_perm = row[2]
        if encoded_perm:
            perm = [(encoded_perm >> (n<<2)) & 0xf for n in range(num)]
            M._reindex_cusps(perm)
        # This seems to be necessary to make the triangulation
        # structure consistent.
        M.dehn_fill([(0,0)]*num)
                
    def keys(self):
        """
        Return the list of column names for this manifold table.
        """
        return self.schema.keys()
    
    def find(self, where, order_by='id', limit=None):
        """
        Return a list of up to limit manifolds stored in this table,
        satisfying the where clause, and ordered by the order_by
        clause.  If limit is None, all matching manifolds are
        returned.  The where clause is a required parameter.
        """
        where_clause = where
        if self._filter:
            where_clause += ' and ' + self._filter
        if limit is None:
            suffix = 'where %s order by %s'%(where_clause, order_by)
        else:
            suffix = 'where %s order by %s limit %d'%(
                where_clause, order_by, limit)
        cursor = self._connection.execute(self._select + suffix)
        return cursor.fetchall()

    def siblings(self, mfld):
        """
        Return all manifolds in the census which have the same hash value.
        """
        return self.find("hash = X'%s'"%self.mfld_hash(mfld))

    def identify(self, mfld, extends_to_link=False):
        """
        Look for a manifold in this table which is isometric to the
        argument.

        Return the matching manifold, if there is one which SnapPea
        declares to be isometric.

        Return False if no manifold in the table has the same hash.

        Return None in all other cases (for now).

        If the flag "extends_to_link" is True, requires that the isometry
        sends meridians to meridians.  
        """
        mfld = mfld.copy()
        sibs = self.siblings(mfld)
        if len(sibs) == 0:
            return False # No hash values match
                # Check for isometry
        for N in sibs:
            try:
                if not extends_to_link:
                    if mfld.is_isometric_to(N):
                        return N
                else:
                    isoms = mfld.is_isometric_to(N, True)
                    if True in [i.extends_to_link() for i in isoms]:
                        return N
            except RuntimeError:
                pass

        # Check for identical triangulations.
        if not False in mfld.cusp_info('is_complete'):
            for n in range(100):
                for N in sibs:
                    if mfld == N:
                        return N
                mfld.randomize()
        
        return None

    def random(self):
        return self[random.randrange(len(self))]
        

class ClosedManifoldTable(ManifoldTable):

    _select = 'select name, triangulation, m, l from %s '

    def __call__(self, **kwargs):
        return ClosedManifoldTable(self._table, **kwargs)

    def _finalize(self, M, row):
        """
        Give the closed manifold a name and do the Dehn filling.
        """
        M.set_name(row[0])
        M.dehn_fill(row[2:4])

class OneCensusManifold():
    """
    Looks up a single manifold by name from the tables provided.
    Returns a tuple: use_string, cobs, perm, triangulation_data .
    """
    _query = "select triangulation, perm from %s where name='%s'"

    def __init__(self, tables, db_path=database_path):
        self._tables = tables
        self._connection = sqlite3.connect(db_path)

    def __call__(self, name):
        for table in self._tables:
            query = self._query%(table, name)
            cursor = self._connection.execute(query)
            rows = cursor.fetchmany(2)
            if len(rows) > 1:
                raise ValueError('Manifold name is ambiguous')
            if len(rows) == 1:
                break
        if len(rows) == 0:
            raise KeyError('The manifold %s was not found.'%name)
        buf = bytes(rows[0][0])
        encoded_perm = rows[0][1]
        header = byte_to_int(buf[0])
        use_cobs, use_string = header&USE_COBS, header&USE_STRING
        num_cusps = header&CUSP_MASK
        cobs = None
        if use_string:
            triangulation_data = buf[1:]
        else:
            triangulation_data = buf[4*num_cusps +1:]
            if use_cobs:
                cobs = decode_matrices(buf[1:4*num_cusps + 1])
        if encoded_perm:
            perm = [(encoded_perm >> (n<<2)) & 0xf for n in range(num_cusps)]
        else:
            perm = None
        return use_string, cobs, perm, triangulation_data

class OrientableCuspedTable(ManifoldTable):
    """
    Iterator for all orientable cusped hyperbolic manifolds that
    can be triangulated with at most 8 ideal tetrahedra.

    >>> for M in OrientableCuspedCensus[3:6]: print(M, M.volume())
    ... 
    m007(0,0) 2.5689706009
    m009(0,0) 2.6667447834
    m010(0,0) 2.66674478345
    >>> for M in OrientableCuspedCensus[-3:]: print(M, M.volume())
    ... 
    t12843(0,0)(0,0) 8.1195328513
    t12844(0,0)(0,0) 8.1195328513
    t12845(0,0)(0,0) 8.1195328513
    >>> for M in OrientableCuspedCensus[4.10:4.12]: print(M, M.volume())
    ... 
    m217(0,0) 4.1079530966
    m218(0,0) 4.1094265923
    m219(0,0) 4.1128528985
    m220(0,0) 4.11696873639
    m221(0,0) 4.1169687364
    s124(0,0) 4.11133100457
    s125(0,0) 4.11370643634
    >>> for M in OrientableCuspedCensus(num_cusps=2)[:3]:
    ...   print(M, M.volume(), M.num_cusps())
    ... 
    m125(0,0)(0,0) 3.6638623767 2
    m129(0,0)(0,0) 3.6638623767 2
    m202(0,0)(0,0) 4.05976642564 2
    >>> M = Manifold('m129')
    >>> M in LinkExteriors
    True
    >>> LinkExteriors.identify(M)
    5^2_1(0,0)(0,0)
    """
    def __init__(self, **kwargs):
       return ManifoldTable.__init__(self,
                                     table='orientable_cusped_view',
                                     **kwargs) 

class NonorientableCuspedTable(ManifoldTable):
    """
    Iterator for all orientable cusped hyperbolic manifolds that
    can be triangulated with at most 5 ideal tetrahedra.

    >>> for M in NonorientableCuspedCensus(betti=2)[:3]:
    ...   print(M, M.homology())
    ... 
    m124(0,0)(0,0)(0,0) Z/2 + Z + Z
    m128(0,0)(0,0) Z + Z
    m131(0,0) Z + Z
    """
    def __init__(self, **kwargs):
       return ManifoldTable.__init__(self,
                                     table='nonorientable_cusped_view',
                                     **kwargs)

class RolfsenTable(ManifoldTable):
    """
    Iterator for all knots with at most 11 crossings and links with
    at most 10 crossings, using the Rolfsen notation.  The triangulations
    were computed by Joe Christy.

    >>> for K in LinkExteriors(num_cusps=3)[-3:]:
    ...   print(K, K.volume())
    ... 
    10^3_72(0,0)(0,0)(0,0) 14.3576890257
    10^3_73(0,0)(0,0)(0,0) 15.8637443096
    10^3_74(0,0)(0,0)(0,0) 15.5509143828
    >>> M = Manifold('8_4')
    >>> OrientableCuspedCensus.identify(M)
    s862(0,0)

    By default, the 'identify' returns the first isometric manifold it finds;
    if the optional 'extends_to_link' flag is set, it insists that meridians
    are taken to meridians.

    >>> M = Manifold('7^2_8')
    >>> LinkExteriors.identify(M)
    5^2_1(0,0)(0,0)
    >>> LinkExteriors.identify(M, extends_to_link=True)
    7^2_8(0,0)(0,0)
    """
    def __init__(self, **kwargs):
       return ManifoldTable.__init__(self,
                                     table='link_exteriors_view',
                                     **kwargs)

    def __call__(self, *args, **kwargs):
        if args: # backwards compatibility for LinkExteriors
            if not isinstance(args[0], int) or len(args) > 1:
                raise TypeError('Invalid specification for num_cusps.')
            if not kwargs.has_key('num_cusps'):
                kwargs['num_cusps'] = args[0]
        return self.__class__(**kwargs)

class HTLinkTable(ManifoldTable):
    """
    Iterator for all knots and links up to 14 crossings as tabulated
    by Jim Hoste and Morwen Thistlethwaite.  In addition to the filter
    arguments supported by all ManifoldTables, this iterator provides
    alternating=<True/False>; knots_vs_links=<'knots'/'links'>; and
    crossings=N. These allow iterations only through alternating or
    non-alternating links with 1 or more than 1 component and a
    specified crossing number.

    >>> HTLinkExteriors.identify(LinkExteriors['8_20'])
    K8n1(0,0)
    >>> Mylist = HTLinkExteriors(alternating=False,knots_vs_links='links')[8.5:8.7]
    >>> len(Mylist)
    8
    >>> for L in Mylist:
    ...   print( L.name(), L.num_cusps(), L.volume() )
    ... 
    L11n138 2 8.6642145442
    L12n1097 2 8.5191836040
    L14n13364 2 8.6933834220
    L14n13513 2 8.5843946543
    L14n15042 2 8.6642145442
    L14n24425 2 8.6067609201
    L14n24777 2 8.5312309303
    L14n26042 2 8.6433378237
    >>> for L in Mylist:
    ...   print( L.name(), L.DT_code() )
    ... 
    L11n138 [(8, -10, -12), (6, -16, -18, -22, -20, -2, -4, -14)]
    L12n1097 [(10, 12, -14, -18), (22, 2, -20, 24, -6, -8, 4, 16)]
    L14n13364 [(8, -10, 12), (6, -18, 20, -22, -26, -24, 2, -4, -28, -16, -14)]
    L14n13513 [(8, -10, 12), (6, -20, 18, -26, -24, -4, 2, -28, -16, -14, -22)]
    L14n15042 [(8, -10, 14), (12, -16, 18, -22, 24, 2, 26, 28, 6, -4, 20)]
    L14n24425 [(10, -12, 14, -16), (-18, 26, -24, 22, -20, -28, -6, 4, -2, 8)]
    L14n24777 [(10, 12, -14, -18), (2, 28, -22, 24, -6, 26, -8, 4, 16, 20)]
    L14n26042 [(10, 12, 14, -20), (8, 2, 28, -22, -24, -26, -6, -16, -18, 4)]
    """

    _select = 'select name, triangulation, perm, DT from %s '

    def __init__(self, **kwargs):
       return ManifoldTable.__init__(self,
                                     table='HT_links_view',
                                     db_path=alt_database_path,
                                     **kwargs)

    def _manifold_factory(self, cursor, row):
        """
        Factory for "select name, triangulation" queries.
        Returns a Manifold with a DT code.
        """
        buf = bytes(row[1])
        header = byte_to_int(buf[0])
        use_cobs, use_string = header&USE_COBS, header&USE_STRING
        num_cusps = header&CUSP_MASK
        M = snappy.Manifold('empty')
        M._set_DTcode(row[3])
        if use_string:
            M._from_string(buf[1:])
        else:
            M._from_bytes(buf[4*num_cusps + 1:])
            if use_cobs:
                cobs = decode_matrices(buf[1:4*num_cusps + 1])
                M.set_peripheral_curves('combinatorial')
                M.set_peripheral_curves(cobs)
        self._finalize(M, row)
        return M

    def _configure(self, **kwargs):
        """
        Process the ManifoldTable filter arguments and then add
        the ones which are specific to links.
        """
        ManifoldTable._configure(self, **kwargs)
        filter = self._filter
        conditions = []

        alt = kwargs.get('alternating', None)
        if alt == True:
            conditions.append("name like '%a%'")
        elif alt == False:
            conditions.append("name like '%n%'")
        flavor = kwargs.get('knots_vs_links', None)
        if flavor == 'knots':
            conditions.append('cusps=1')
        elif flavor == 'links':
            conditions.append('cusps>1')
        if 'crossings' in kwargs:
            N = int(kwargs['crossings'])
            conditions.append(
                "(name like '%%_%da%%' or name like '%%_%dn%%')"%(N,N))
        if self._filter:
            if len(conditions) > 0:
                self._filter += (' and ' + ' and '.join(conditions))
        else:
            self._filter = ' and '.join(conditions)

class CensusKnotsTable(ManifoldTable):
    """
    Iterator for all of the knot exteriors in the SnapPea Census, as
    tabulated by Callahan, Dean, Weeks, Champanerkar, Kofman and
    Patterson.  These are the knot exteriors which can be triangulated
    by at most 7 ideal tetrahedra.
    
    >>> for M in CensusKnots[3.4:3.5]:
    ...   print(M, M.volume(), LinkExteriors.identify(M))
    ... 
    K4_3(0,0) 3.47424776131 False
    K5_1(0,0) 3.4179148372 False
    K5_2(0,0) 3.42720524627 8_1(0,0)
    K5_3(0,0) 3.48666014630 9_2(0,0)
    """
    def __init__(self, **kwargs):
       return ManifoldTable.__init__(self,
                                     table='census_knots_view',
                                     **kwargs) 

class OrientableClosedTable(ClosedManifoldTable):
    """
    Iterator for 11,031 closed hyperbolic manifolds from the census by
    Hodgson and Weeks.

    >>> len(OrientableClosedCensus)
    11031
    >>> len(OrientableClosedCensus(betti=2))
    1
    >>> for M in OrientableClosedCensus(betti=2):
    ...   print(M, M.homology())
    ... 
    v1539(5,1) Z + Z
    """
    def __init__(self, **kwargs):
       return ClosedManifoldTable.__init__(self,
                                           table='orientable_closed_view',
                                           **kwargs) 

class NonorientableClosedTable(ClosedManifoldTable):
    """
    Iterator for 17 nonorientable closed hyperbolic manifolds from the
    census by Hodgson and Weeks.
    
    >>> for M in NonorientableClosedCensus[:3]: print(M, M.volume())
    ... 
    m018(1,0) 2.02988321282
    m177(1,0) 2.568970601
    m153(1,0) 2.6667447834
    """
    def __init__(self, **kwargs):
       return ClosedManifoldTable.__init__(self,
                                           table='nonorientable_closed_view',
                                           **kwargs) 


# Instantiate our tables ...
try:
    OrientableCuspedCensus = OrientableCuspedTable()
    NonorientableCuspedCensus = NonorientableCuspedTable()
    OrientableClosedCensus = OrientableClosedTable()
    NonorientableClosedCensus = NonorientableClosedTable()
    LinkExteriors = RolfsenTable()
    CensusKnots = CensusKnotsTable()

# ... and the individual lookup objects for the Manifold class
    CuspedManifoldData = OneCensusManifold( ['orientable_cusped_view',
                                             'nonorientable_cusped_view'] )
    LinkExteriorData = OneCensusManifold( ['link_exteriors_view'] )
    CensusKnotData = OneCensusManifold( ['census_knots_view'] )
except (KeyError, AssertionError):
    pass

# Separately instantiate the big data for those who have it ...
try:
    HTLinkExteriors = HTLinkTable()
    HTLinkExteriorData = OneCensusManifold( ['HT_links_view'],
                                            db_path=alt_database_path)
except (sqlite3.OperationalError, KeyError, AssertionError):
    pass

# Test routines.
def test_census_database():
    L = OrientableCuspedDB
    for M in CensusKnots():
        print(M, L.identify(M))

def test():
    import re
    pairs = [ (CensusKnots(), CensusKnotsDB),
              (OrientableCuspedCensus(), OrientableCuspedDB)]
    for census, db in pairs:
        for M in census:
            if M.name()[0] == 't':
                break
            N = db.identify(M)
            assert repr(M) == repr(N)
            G, H = M.fundamental_group(), N.fundamental_group()
            if (G.relators() != H.relators() or
                G.peripheral_curves() != H.peripheral_curves()):
                print(M)

if __name__ == '__main__':
    test()
