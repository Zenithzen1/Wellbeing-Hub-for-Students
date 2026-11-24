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
    def __init__(self):
        """Empty queue. O(1)"""
        self.arr = []
        self.len = 0

    def __len__(self): 
        """Number of keys held. O(1)"""
        return self.len

    def _upheap(self, idx = 0):
        curr = self.len - 1 if idx == 0 else idx
        parent = (curr - 1) // 2
        while curr != 0:
            if self.arr[curr] < self.arr[parent]:
                self.arr[curr], self.arr[parent] = self.arr[parent], self.arr[curr]

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

            self.arr[curr], self.arr[smallerChild] = self.arr[smallerChild], self.arr[curr]
            curr = smallerChild

            leftChild = 2 * curr + 1
            rightChild = 2 * curr + 2
    
    def insert(self, key): 
        """Add a key. O(log n)"""
        self.arr.append(key)
        self.len += 1
        self._upheap()
    
    def get_min(self): 
        """Smallest key, kept. O(1)"""
        if self.len == 0:
            return None
        return self.arr[0]


    def extract_min(self): 
        """Remove + return it. O(log n)"""

        if self.len == 0:
            return None
        
        self.arr[0], self.arr[self.len - 1] = self.arr[self.len - 1], self.arr[0]

        minimum = self.arr.pop()
        self.len -= 1

        self._downheap()

        return minimum

        
    def delete(self, key): 
        """Remove one key. O(n) + O(log n)"""

        found = False

        for idx in range(self.len):
            if self.arr[idx] == key:
                self.arr[idx], self.arr[-1] = self.arr[-1], self.arr[idx]
                found = True
                break

        if found:
            remove = self.arr.pop()
            self.len -= 1

            if idx > 0 and self.arr[idx] < self.arr[(idx - 1) // 2]:
                self._upheap(idx)
            else:
                self._downheap(idx)
            return remove

        else: 
            return None
    
    def update_key(self, old, new): 
        """Change a key. O(n) + O(log n)"""

        found = False
        
        for idx in range(self.len):
            if self.arr[idx] == old:
                self.arr[idx] = new
                found = True
                break

        if found:
            if idx > 0 and self.arr[idx] < self.arr[(idx - 1) // 2]:
                self._upheap(idx)
            else:
                self._downheap(idx)


    def build_heap(self, array): 
        """Heapify an array. O(n)"""

        self.arr = array
        self.len = len(array)

        for i in range(len(array) // 2 - 1, -1, -1):
            self._downheap(i) 

    pass

class AVLTree:
    #TODO
    pass

class IntervalTree:
    #TODO
    pass

class Graph:
    #TODO
    pass