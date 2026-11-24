#Personal Implementation of Data Structures to use in Project

class DynamicArray:
    #TODO
    pass

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