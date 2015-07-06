"""
A collection of Python classes and objects which replace various
features of Sage; the purpose of these is to allow some of the
snappy.snap tools to be used in an environment where Sage is not
available.

"""
from snappy.number import SnapPyNumbers, Number, is_exact
from itertools import chain

class MatrixBase(object):
    """Base class for Vector2 and Matrix2x2. Do not instantiate."""
    _base_ring = None
    
    def base_ring(self):
        """If a base ring was set when initializing the matrix, then this
        method will return that ring.  Otherwise, the base ring is a
        SnapPyNumbers object whose precision is the maximum precision
        of the elements.  If a new Number is created using the computed
        base ring and combined with the entries of this matrix, then the
        precision of the result will be determined by the precisions of
        the entries.  

        """
        if self._base_ring:
            return self._base_ring
        else:
            precision = max([x.prec() for x in self.list()])
            return SnapPyNumbers(precision=precision)

    def list(self):
        #Override this
        return []
        
class Vector2(MatrixBase):
    """A 2-dimensional vector whose entries are snappy Numbers."""
    def __init__(self, *args):
        if isinstance(args[0], SnapPyNumbers):
            self._base_ring = number = args[0]
            args = args[1:]
        else:
            self._base_ring = None
            number = Number
        if len(args) == 1:
            args = args[0]    
        if len(args) == 2:
            self.x, self.y = [number(t) for t in args]
        else:
            raise ValueError('Invalid initialization for a 2d vector.') 

    def __getitem__(self, index):
        if index == 0:
            return self.x
        elif index == 1:
            return self.y
        else:
            raise IndexError('Invalid Vector2 index.')
        
    def __repr__(self):
        entries = map(str, self.list())
        size = max(map(len, entries))
        entries = tuple(('%%-%d.%ds'%(size,size))%x for x in entries)
        return '[ %s ]\n[ %s ]'%entries

    def __add__(self, other):
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Vector2(self.x - other.x, self.y - other.y)

    def __mul__(self, other):        
        if isinstance(other, Matrix2x2):
            return Vector2(self.x * other.a + self.y * other.c,
                           self.x * other.b + self.y * other.d)
        else:
            return Vector2(self.x * other, self.y * other)

    def __rmul__(self, other):        
            return Vector2(self.x * other, self.y * other)

    def __neg__(self):
        return Vector2(-self.x, -self.y)

    def list(self):
        return [self.x, self.y]
    
class Matrix2x2(MatrixBase):
    """A 2x2 matrix class whose entries are snappy Numbers."""
    def __init__(self, *args):
        if isinstance(args[0], SnapPyNumbers):
            self._base_ring = number = args[0]
            args = args[1:]
        else:
            self._base_ring = None
            number = Number
        if len(args) == 1:
            args = tuple(chain(*args[0]))    
        if len(args) == 4:
            self.a, self.b, self.c, self.d = [number(x) for x in args]
        else:
            raise ValueError('Invalid initialization for a 2x2 matrix.') 

    def __repr__(self):
        entries = map(str, self.list())
        size = max(map(len, entries))
        entries = tuple(('%%-%d.%ds'%(size,size))%x for x in entries)
        return '[ %s  %s ]\n[ %s  %s ]'%entries

    def __getitem__(self, index):
        if isinstance(index, int):
            if index == 0:
                return [self.a, self.b]
            elif index == 1:
                return [self.c, self.d]
        elif isinstance(index, tuple) and len(index) == 2:
            i, j = index
            if   i == 0:
                return self.a if j == 0 else self.b
            elif i == 1:
                return self.c if j == 0 else self.d
        raise IndexError('Invalid 2x2 matrix index.')
            
    def __add__(self, other):
        return Matrix2x2(self.a + other.a,
                         self.b + other.b,
                         self.c + other.c,
                         self.d + other.d)

    def __sub__(self, other):
        return Matrix2x2(self.a - other.a,
                         self.b - other.b,
                         self.c - other.c,
                         self.d - other.d)

    def __mul__(self, other):
        if isinstance(other, Matrix2x2):
            return Matrix2x2(self.a * other.a + self.b * other.c,
                             self.a * other.b + self.b * other.d,
                             self.c * other.a + self.d * other.c,
                             self.c * other.b + self.d * other.d)
        if isinstance(other, Vector2):
            return Vector2(self.a * other.x + self.b * other.y,
                           self.c * other.x + self.d * other.y)
        else:
            return Matrix2x2(self.a * other, self.b * other,
                             self.c * other, self.d * other)
        
    def __rmul__(self, other):
        # This will not be called if other is a Matrix2x2
        return Matrix2x2(self.a * other, self.b * other,
                         self.c * other, self.d * other)

    def __neg__(self):
        return Matrix2x2(-self.a, -self.b, -self.c, -self.d)
    
    def __invert__(self):
        # Should we deal with rings?
        try:
            D = 1/self.det()
        except ZeroDivisionError:
            raise ZeroDivisionError('matrix %s is not invertible.'%self)
        return Matrix2x2(self.d*D, -self.b*D, -self.c*D, self.a*D)

    def det(self):
        return self.a * self.d - self.b * self.c

    def trace(self):
        return self.a + self.d
    
    def adjoint(self):
        return Matrix2x2(self.d, -self.b, -self.c, self.a)

    def list(self):
        return [self.a, self.b, self.c, self.d]


def indexset(n):
    """The orders of the non-zero bits in the binary expansion of n."""
    i = 0
    result = []
    while True:
        mask = 1<<i
        if n & mask:
            result.append(i)
        if n < mask:
            break
        i += 1
    return result

def powerset(X):
    """Iterator for all finite subsequences of the iterable X"""
    n = 0
    segment = []
    for x in X:
        segment.append(x)
        while True:
            try:
                yield [ segment[i] for i in indexset(n) ]
            except IndexError:
                break
            n += 1

