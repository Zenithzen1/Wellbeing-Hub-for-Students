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
    #TODO
    pass

class IndexedMinHeap:
    def __init__(self):
        """Empty queue. O(1)"""
        self.arr = []
        self.len = 0
        self.pos = {}   # key -> index in self.arr (keys must be unique + hashable)

    def __len__(self):
        """Number of keys held. O(1)"""
        return self.len

    def _swap(self, i, j):
        self.arr[i], self.arr[j] = self.arr[j], self.arr[i]
        self.pos[self.arr[i]] = i
        self.pos[self.arr[j]] = j

    def _upheap(self, idx = None):
        curr = self.len - 1 if idx is None else idx
        parent = (curr - 1) // 2
        while curr != 0:
            if self.arr[curr] < self.arr[parent]:
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
            if rightChild < (self.len if limit is None else limit) and self.arr[rightChild] < self.arr[leftChild]:
                smallerChild = rightChild
            else:
                smallerChild = leftChild

            if self.arr[curr] <= self.arr[smallerChild]:
                break

            self._swap(curr, smallerChild)
            curr = smallerChild

            leftChild = 2 * curr + 1
            rightChild = 2 * curr + 2
    
    def insert(self, key): 
        """Add a key. O(log n)"""
        if key in self.pos:
            raise ValueError("Key already in heap")

        self.arr.append(key)
        self.pos[key] = self.len
        self.len += 1
        self._upheap()
    
    def get_min(self): 
        """Smallest key, kept. O(1)"""
        if self.len == 0:
            raise IndexError("get_min from empty heap")
        return self.arr[0]


    def extract_min(self): 
        """Remove + return it. O(log n)"""

        if self.len == 0:
            raise IndexError("extract_min from empty heap")
        
        self._swap(0, self.len - 1)

        minimum = self.arr.pop()
        del self.pos[minimum]
        self.len -= 1

        self._downheap()

        return minimum

        
    def delete(self, key): 
        """Remove one key. O(log n)"""

        idx = self.pos.get(key)
        found = idx is not None

        if found:
            self._swap(idx, self.len - 1)

            remove = self.arr.pop()
            del self.pos[remove]
            self.len -= 1

            if idx == self.len:     # removed key was the last element, nothing to fix
                return remove

            if idx > 0 and self.arr[idx] < self.arr[(idx - 1) // 2]:
                self._upheap(idx)
            else:
                self._downheap(idx)
            return remove

        else:
            raise KeyError(key)
    
    def update_key(self, old, new): 
        """Change a key. O(log n)"""

        idx = self.pos.get(old)
        found = idx is not None

        if found:
            if new != old and new in self.pos:
                raise ValueError("Key already in heap")

            del self.pos[old]
            self.arr[idx] = new
            self.pos[new] = idx

            if idx > 0 and self.arr[idx] < self.arr[(idx - 1) // 2]:
                self._upheap(idx)
            else:
                self._downheap(idx)

        else:
            raise KeyError(old)

    def build_heap(self, array):
        """Heapify an array. O(n)"""

        pos = {key: i for i, key in enumerate(array)}
        if len(pos) != len(array):
            raise ValueError("Duplicate keys in array")

        self.arr = list(array)
        self.len = len(array)
        self.pos = pos

        for i in range(len(array) // 2 - 1, -1, -1):
            self._downheap(i)

class AVLTree:
    #TODO
    pass

class IntervalTree:
    #TODO
    pass

class Graph:
    #TODO
    pass