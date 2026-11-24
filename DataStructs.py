#Personal Implementation of Data Structures to use in Project

class DynamicArray:
    def __init__(self):
        self.capacity = 2
        self.size = 0
        self.array = [None] * self.capacity

    def __len__(self):
        return self.size

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
        self.array[index] = None


        for i in range(index, self.size):
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
    #TODO
    pass

class IndexedMinHeap:
    #TODO
    pass

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
    #TODO
    pass