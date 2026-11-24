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
        self.queue = []
        self.len = 0

    def enqueue(self, val):
        self.append(val)
        self.len += 1

    def dequeue(self):
        val = self.pop(0)
        self.len -= 1
        return val

    def peek(self):
        return self.queue[0]

    def is_empty(self):
        return self.len == 0

    def __len__(self):
        return self.len

class HashMap:
    #TODO
    pass

class IndexedMinHeap:
    #TODO
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