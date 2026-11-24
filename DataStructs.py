#Personal Implementation of Data Structures to use in Project

class DynamicArray:
    def __init__(self):
        self.capacity = 2
        self.size = 0
        self.array = [None] * self.capacity

    def __len__(self):
        return self.size

    def __getitem__(self, index):
        if index < 0 or index >= self.size:
            raise IndexError("Index out of bounds")
        return self.array[index]

    def __setitem__(self, index, element):
        if index < 0 or index >= self.size:
            raise IndexError("Index out of bounds")
        self.array[index] = element

    def __iter__(self):
        for i in range(self.size):
            yield self.array[i]

    def _resize(self, newCapacity):
        newArray = [None] * newCapacity

        for i in range(self.size):
            newArray[i] = self.array[i]

        self.array = newArray
        self.capacity = newCapacity

    def append(self, element):
        if self.size == self.capacity:
            self._resize( self.capacity * 2 )

        self.array[self.size] = element
        self.size += 1

    def insert(self, index, element):
        if index < 0 or index > self.size:
            raise IndexError("Index out of bounds")

        if self.size == self.capacity:
            self._resize( self.capacity * 2 )

        for i in range(self.size, index, -1):
            self.array[i] = self.array[i - 1]

        self.array[index] = element
        self.size += 1

    def pop(self, index = None):
        if index is None:
            index = self.size - 1

        if self.size == 0:
            raise IndexError("Pop from empty array")

        if index < 0 or index >= self.size:
            raise IndexError("Index out of bounds")

        element = self.array[index]

        for i in range(index, self.size - 1):
            self.array[i] = self.array[i + 1]

        self.size -= 1
        self.array[self.size] = None

        if (self.size > 0) and (self.size == self.capacity // 4):
            self._resize( self.capacity // 2)

        return element

class Queue:
    def __init__(self):
        self.capacity = 2
        self.queue = [None] * 2

        self.front = 0
        self.rear = 0
        self.size = 0

    def __len__(self):
        return self.size

    def is_empty(self):
        return not self.size

    def _resize(self, newCapacity):
        newArray = [None] * newCapacity

        for i in range(self.size):
            newArray[i] = self.queue[(self.front + i) % self.capacity]

        self.queue = newArray
        self.capacity = newCapacity
        self.front = 0
        self.rear = self.size


    def enqueue(self, element):
        if self.size == self.capacity:
            self._resize(self.capacity * 2) 

        self.queue[self.rear] = element
        self.rear = (self.rear + 1) % self.capacity
        self.size += 1

    def dequeue(self):
    
        if self.size == 0:
            raise IndexError("Dequeue from empty queue")

        element = self.queue[self.front]
        self.queue[self.front] = None

        self.front = (self.front + 1) % self.capacity
        self.size -= 1

        if self.size > 0 and self.size == self.capacity // 4:
            self._resize(self.capacity // 2 )

        return element
    
    def peek(self):
        if self.size == 0:
            raise IndexError("Peek from empty queue")
        return self.queue[self.front]

class HashMap:
    """Hash map with separate chaining (plan section 3.3).

    An array of buckets; each bucket is a linked chain of (key, value) nodes.
    A key's bucket is FNV-1a(key bytes) mod the number of buckets. When the load
    factor (keys / buckets) goes over 0.75 the array doubles and every node is
    re-inserted, so get / put / remove are O(1) on average.
    """

    INITIAL_CAPACITY = 8
    MAX_LOAD = 0.75

    class _Node:
        __slots__ = ("key", "value", "hash", "next")

        def __init__(self, key, value, hash, next):
            self.key = key
            self.value = value
            self.hash = hash      # full FNV-1a value, kept so a resize needn't re-hash
            self.next = next

    def __init__(self):
        """Empty map. O(1)"""
        self.capacity = self.INITIAL_CAPACITY
        self.buckets = [None] * self.capacity
        self.size = 0

    def __len__(self):
        """Number of keys. O(1)"""
        return self.size

    @staticmethod
    def _fnv1a(data):
        """64-bit FNV-1a hash of a bytes object."""
        h = 0xcbf29ce484222325
        for byte in data:
            h ^= byte
            h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
        return h

    @staticmethod
    def _key_bytes(key):
        """Bytes to hash for a key. Keys that are == must give the same bytes."""
        if isinstance(key, str):
            return key.encode("utf-8", "surrogatepass")
        if isinstance(key, bytes):
            return key
        if isinstance(key, tuple):    # e.g. (week, category); length-prefix each part
            out = b""
            for part in key:
                part = HashMap._key_bytes(part)
                out += len(part).to_bytes(4, "little") + part
            return out
        # Numbers and other hashable keys: Python's hash() agrees with ==, so
        # 1, 1.0 and True share a bucket. Unhashable keys raise TypeError here.
        return hash(key).to_bytes(8, "little", signed=True)

    def _hash(self, key):
        return self._fnv1a(self._key_bytes(key))

    def _find(self, key):
        h = self._hash(key)
        node = self.buckets[h % self.capacity]
        while node is not None:
            if node.hash == h and (node.key is key or node.key == key):
                return node
            node = node.next
        return None

    def _resize(self, newCapacity):
        oldBuckets = self.buckets
        self.capacity = newCapacity
        self.buckets = [None] * newCapacity

        for node in oldBuckets:
            while node is not None:
                nextNode = node.next
                index = node.hash % newCapacity
                node.next = self.buckets[index]
                self.buckets[index] = node
                node = nextNode

    def put(self, key, value):
        """Insert key, or overwrite its value. O(1) average, amortised"""
        h = self._hash(key)
        index = h % self.capacity

        node = self.buckets[index]
        while node is not None:
            if node.hash == h and (node.key is key or node.key == key):
                node.value = value
                return
            node = node.next

        self.buckets[index] = self._Node(key, value, h, self.buckets[index])
        self.size += 1

        if self.size > self.capacity * self.MAX_LOAD:
            self._resize(self.capacity * 2)

    def get(self, key, default = None):
        """Value for key, or default if missing. O(1) average"""
        node = self._find(key)
        return default if node is None else node.value

    def remove(self, key):
        """Delete key and return its value. KeyError if missing. O(1) average"""
        h = self._hash(key)
        index = h % self.capacity

        prev, node = None, self.buckets[index]
        while node is not None:
            if node.hash == h and (node.key is key or node.key == key):
                if prev is None:
                    self.buckets[index] = node.next
                else:
                    prev.next = node.next
                self.size -= 1
                return node.value
            prev, node = node, node.next

        raise KeyError(key)

    def contains(self, key):
        """Is key in the map? O(1) average"""
        return self._find(key) is not None

    def items(self):
        """List of (key, value) pairs, in no particular order. O(n)"""
        pairs = []
        for node in self.buckets:
            while node is not None:
                pairs.append((node.key, node.value))
                node = node.next
        return pairs

    def keys(self):
        """List of keys, in no particular order. O(n)"""
        return [key for key, _ in self.items()]

    def values(self):
        """List of values, in no particular order. O(n)"""
        return [value for _, value in self.items()]

    def clear(self):
        """Remove everything. O(1)"""
        self.__init__()

    # dict-style shortcuts: m[k], m[k] = v, del m[k], k in m, for k in m
    def __getitem__(self, key):
        node = self._find(key)
        if node is None:
            raise KeyError(key)
        return node.value

    def __setitem__(self, key, value):
        self.put(key, value)

    def __delitem__(self, key):
        self.remove(key)

    def __contains__(self, key):
        return self.contains(key)

    def __iter__(self):
        return iter(self.keys())

class IndexedMinHeap:
    """Min-heap of (id, key) entries plus a position map id -> array index
    (plan sections 5 and 7), so an entry can be removed or re-prioritised by id.

    Each id appears at most once. Smaller key = served first; entries with equal
    keys come out in no particular order (use e.g. key = (send_at, id) if ties
    must be deterministic).
    """

    def __init__(self):
        """Empty heap. O(1)"""
        self.arr = []           # (id, key) entries in heap order
        self.len = 0
        self.pos = HashMap()    # id -> index in self.arr

    def __len__(self):
        """Number of entries. O(1)"""
        return self.len

    def __contains__(self, id):
        return self.contains(id)

    def _less(self, i, j):
        return self.arr[i][1] < self.arr[j][1]

    def _swap(self, i, j):
        self.arr[i], self.arr[j] = self.arr[j], self.arr[i]
        self.pos.put(self.arr[i][0], i)
        self.pos.put(self.arr[j][0], j)

    def _upheap(self, idx = None):
        curr = self.len - 1 if idx is None else idx
        parent = (curr - 1) // 2
        while curr != 0:
            if self._less(curr, parent):
                self._swap(curr, parent)

                curr = parent
                parent = (parent - 1) // 2
            else:
                break

    def _downheap(self,  idx = None, limit = None):
        curr = 0 if idx is None else idx
        leftChild = 2 * curr + 1
        rightChild = 2 * curr + 2

        while leftChild < (self.len if limit is None else limit):
            if rightChild < (self.len if limit is None else limit) and self._less(rightChild, leftChild):
                smallerChild = rightChild
            else:
                smallerChild = leftChild

            if not self._less(smallerChild, curr):
                break

            self._swap(curr, smallerChild)
            curr = smallerChild

            leftChild = 2 * curr + 1
            rightChild = 2 * curr + 2
    
    def push(self, id, key):
        """Add id with priority key. ValueError if id is already in. O(log n)"""
        if self.pos.contains(id):
            raise ValueError("id already in heap")

        self.arr.append((id, key))
        self.pos.put(id, self.len)
        self.len += 1
        self._upheap()

    def peek(self):
        """(id, key) with the smallest key, kept. O(1)"""
        if self.len == 0:
            raise IndexError("peek from empty heap")
        return self.arr[0]

    def pop(self):
        """Remove + return (id, key) with the smallest key. O(log n)"""

        if self.len == 0:
            raise IndexError("pop from empty heap")

        self._swap(0, self.len - 1)

        minimum = self.arr.pop()
        self.pos.remove(minimum[0])
        self.len -= 1

        self._downheap()

        return minimum

    def remove(self, id):
        """Remove id and return its key. KeyError if missing. O(log n)"""

        idx = self.pos.get(id)
        found = idx is not None

        if found:
            self._swap(idx, self.len - 1)

            removed = self.arr.pop()
            self.pos.remove(id)
            self.len -= 1

            if idx == self.len:     # removed entry was the last element, nothing to fix
                return removed[1]

            if idx > 0 and self._less(idx, (idx - 1) // 2):
                self._upheap(idx)
            else:
                self._downheap(idx)
            return removed[1]

        else:
            raise KeyError(id)

    def update(self, id, key):
        """Change id's key. KeyError if missing. O(log n)"""

        idx = self.pos.get(id)
        found = idx is not None

        if found:
            self.arr[idx] = (id, key)

            if idx > 0 and self._less(idx, (idx - 1) // 2):
                self._upheap(idx)
            else:
                self._downheap(idx)

        else:
            raise KeyError(id)

    def contains(self, id):
        """Is id in the heap? O(1)"""
        return self.pos.contains(id)

    def build_heap(self, entries):
        """Replace the contents with these (id, key) pairs, e.g. rows loaded at startup. O(n)"""

        entries = [(id, key) for id, key in entries]
        pos = HashMap()
        for i, (id, _) in enumerate(entries):
            if pos.contains(id):
                raise ValueError("Duplicate ids in entries")
            pos.put(id, i)

        self.arr = entries
        self.len = len(entries)
        self.pos = pos

        for i in range(self.len // 2 - 1, -1, -1):
            self._downheap(i)

class AVLNode:
    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.left = None
        self.right = None
        self.height = 1


class AVLTree:
    def __init__(self):
        self.root = None
        self.size = 0

    def __len__(self):
        return self.size

    def is_empty(self):
        return not self.size

    def _makeNode(self, key, value):
        return AVLNode(key, value)

    def _height(self, node):
        if node is None:
            return 0
        return node.height

    def _update(self, node):
        node.height = 1 + max(self._height(node.left), self._height(node.right))

    def _balance(self, node):
        return self._height(node.left) - self._height(node.right)

    def _rotate_right(self, y):
        x = y.left
        y.left = x.right
        x.right = y
        self._update(y)
        self._update(x)
        return x

    def _rotate_left(self, x):
        y = x.right
        x.right = y.left
        y.left = x
        self._update(x)
        self._update(y)
        return y

    def _rebalance(self, node):
        self._update(node)
        balance = self._balance(node)

        if balance > 1:
            if self._balance(node.left) < 0:
                node.left = self._rotate_left(node.left)
            return self._rotate_right(node)

        if balance < -1:
            if self._balance(node.right) > 0:
                node.right = self._rotate_right(node.right)
            return self._rotate_left(node)

        return node

    def insert(self, key, value=None):
        self.root = self._insert(self.root, key, value)

    def _insert(self, node, key, value):
        if node is None:
            self.size += 1
            return self._makeNode(key, value)

        if key < node.key:
            node.left = self._insert(node.left, key, value)
        elif key > node.key:
            node.right = self._insert(node.right, key, value)
        else:
            node.value = value
            return node

        return self._rebalance(node)

    def _find(self, key):
        node = self.root
        while node is not None:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return node
        return None

    def __contains__(self, key):
        return self._find(key) is not None

    def search(self, key):
        node = self._find(key)
        if node is None:
            raise KeyError("Key not found")
        return node.value

    def in_order(self):
        result = DynamicArray()
        self._in_order(self.root, result)
        return result

    def _in_order(self, node, result):
        if node is None:
            return
        self._in_order(node.left, result)
        result.append(node.key)
        self._in_order(node.right, result)

    def delete(self, key):
        self.root = self._delete(self.root, key)

    def _delete(self, node, key):
        if node is None:
            raise KeyError("Key not found")

        if key < node.key:
            node.left = self._delete(node.left, key)
        elif key > node.key:
            node.right = self._delete(node.right, key)
        else:
            if node.left is None:
                self.size -= 1
                return node.right
            if node.right is None:
                self.size -= 1
                return node.left

            successor = node.right
            while successor.left is not None:
                successor = successor.left

            node.key = successor.key
            node.value = successor.value
            node.right = self._delete(node.right, successor.key)

        return self._rebalance(node)

class IntervalNode(AVLNode):
    def __init__(self, key, value=None):
        super().__init__(key, value)
        self.maxHigh = key[1]


class IntervalTree(AVLTree):
    def _makeNode(self, key, value):
        return IntervalNode(key, value)

    def _update(self, node):
        super()._update(node)
        best = node.key[1]
        if node.left is not None and node.left.maxHigh > best:
            best = node.left.maxHigh
        if node.right is not None and node.right.maxHigh > best:
            best = node.right.maxHigh
        node.maxHigh = best

    def insert(self, low, high, value=None):
        if low > high:
            raise ValueError("low must be <= high")
        super().insert((low, high), value)

    def delete(self, low, high):
        super().delete((low, high))

    def _overlaps(self, node, low, high):
        return node.key[0] <= high and low <= node.key[1]

    def find_overlap(self, low, high):
        if low > high:
            raise ValueError("low must be <= high")
        node = self.root
        while node is not None:
            if self._overlaps(node, low, high):
                return node.key
            if node.left is not None and node.left.maxHigh >= low:
                node = node.left
            else:
                node = node.right
        return None

    def query(self, low, high):
        if low > high:
            raise ValueError("low must be <= high")
        result = DynamicArray()
        self._query(self.root, low, high, result)
        return result

    def _query(self, node, low, high, result):
        if node is None or node.maxHigh < low:
            return
        self._query(node.left, low, high, result)
        if self._overlaps(node, low, high):
            result.append(node.key)
        if node.key[0] <= high:
            self._query(node.right, low, high, result)



class Graph:
    """Undirected weighted graph (student - tag - item) for recommendations (plan section 8).

    Adjacency is a HashMap of HashMaps: node -> (neighbour -> weight), so edge
    lookups, weight updates and removals are O(1) instead of scanning a list.
    Only the plan's HashMap methods (put, get, remove, contains, items) are used.
    """

    def __init__(self):
        """Empty graph. O(1)"""
        self.adj = HashMap()     # node id -> HashMap(neighbour id -> weight)
        self.kinds = HashMap()   # node id -> kind, e.g. "student", "tag", "item"

    def __len__(self):
        """Number of nodes. O(1)"""
        return len(self.adj)

    def __contains__(self, node):
        """Is this node in the graph? O(1)"""
        return self.adj.contains(node)

    def _edges_of(self, node):
        edges = self.adj.get(node)
        if edges is None:
            raise KeyError(node)
        return edges

    def add_node(self, node, kind):
        """Add a node of the given kind. O(1)"""
        if self.adj.contains(node):
            raise ValueError("Node already in graph")

        self.adj.put(node, HashMap())
        self.kinds.put(node, kind)

    def kind(self, node):
        """Kind the node was added with. O(1)"""
        if not self.kinds.contains(node):
            raise KeyError(node)
        return self.kinds.get(node)

    def add_edge(self, u, v, w):
        """Connect u and v with weight w, or overwrite the weight if already connected. O(1)"""
        uEdges = self._edges_of(u)
        vEdges = self._edges_of(v)
        if u == v:
            raise ValueError("Self-loops are not allowed")

        uEdges.put(v, w)
        vEdges.put(u, w)

    def remove_edge(self, u, v):
        """Disconnect u and v. O(1)"""
        if not self.has_edge(u, v):
            raise KeyError((u, v))

        self.adj.get(u).remove(v)
        self.adj.get(v).remove(u)

    def has_edge(self, u, v):
        """Are u and v connected? O(1)"""
        uEdges = self.adj.get(u)
        return uEdges is not None and uEdges.contains(v)

    def weight(self, u, v):
        """Weight of the edge u - v. O(1)"""
        if not self.has_edge(u, v):
            raise KeyError((u, v))
        return self.adj.get(u).get(v)

    def neighbours(self, u):
        """List of (neighbour, weight) pairs. O(deg u)"""
        return self._edges_of(u).items()

    def bfs(self, src, depth = None):
        """(node, hops) pairs within `depth` hops of src, in BFS order, src first. O(V + E) of the part explored"""
        if not self.adj.contains(src):
            raise KeyError(src)
        if depth is not None and depth < 0:
            raise ValueError("depth must be non-negative")

        hops = HashMap()
        hops.put(src, 0)
        order = [(src, 0)]

        queue = Queue()
        queue.enqueue(src)

        while not queue.is_empty():
            u = queue.dequeue()
            d = hops.get(u)
            if depth is not None and d == depth:
                continue

            for v, _ in self.adj.get(u).items():
                if not hops.contains(v):
                    hops.put(v, d + 1)
                    order.append((v, d + 1))
                    queue.enqueue(v)

        return order
