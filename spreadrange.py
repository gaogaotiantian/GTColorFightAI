class SpreadRange:
    def __init__(self, start, end = None):
        if end == None:
            self.start = 1
            self.end = start
        else:
            self.start = start
            self.end = end
        self.waitQueue = [(0, 0)]
        while self.GetDist(self.waitQueue[0]) < self.start:
            self.next()

    def __iter__(self):
        return self

    def next(self):
        curr = self.waitQueue.pop(0)
        currDist = self.GetDist(curr)
        if self.GetDist(curr) >= self.end:
            raise StopIteration()
        for delta in [(0,1), (0,-1), (1,0), (-1,0)]:
            temp = self.Add(curr, delta)
            if self.GetDist(temp) > self.GetDist(curr) and temp not in self.waitQueue:
                self.waitQueue.append(temp)
        return curr

    def GetDist(self, t):
        return abs(t[0]) + abs(t[1])
    
    def Add(self, t1, t2):
        return (t1[0] + t2[0], t1[1] + t2[1])

if __name__ == "__main__":
    a = SpreadRange(5)
    for i in a:
        print i
