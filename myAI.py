# You need to import colorfight for all the APIs
import API.colorfight as colorfight
import random
import json
import time

class EvalPoint:
    def __init__(self, x = None, y = None, attrTable = None):
        self.vals = {}
        self.goldVal = 0
        self.x = x
        self.y = y
        self.attrTable = attrTable
        self.cost = 1
        for attr in self.attrTable:
            self.vals[attr] = 0
    def SetVal(self, valKey, val):
        if valKey == "cost":
            self.cost = val
        else:
            self.vals[valKey] = val
    def AddVal(self, valKey, val):
        if valKey == "cost":
            self.cost += val
        else:
            if valKey not in self.vals:
                self.vals[valKey] = val
            else:
                self.vals[valKey] += val
    def GetVal(self, valKey):
        if valKey == "cost":
            return self.cost
        return self.vals[valKey]
    def TotalVal(self):
        ret = 0
        for k, v in self.vals.items():
            ret = ret + v*self.attrTable[k]["val"]
        return ret/self.cost
    def ToDict(self):
        ret = {"val":self.TotalVal(), "x":self.x, "y":self.y, "cost":self.cost}
        for k, v in self.vals.items():
            ret[k] = v*self.attrTable[k]['val']
        return ret

class EvalMap:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.attrTable = {
            "location": {"val":2},
            "golden": {"val":1},
            "base":{"val":2}
        }
        self.data = [None] * (width*height)
        for i in range(width * height):
            x, y = self.IndexToXY(i)
            self.data[i] = EvalPoint(x, y, self.attrTable)

    def ValidXY(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            return True
        return False

    def IndexToXY(self, idx):
        x = idx%self.width
        y = int(idx/self.width)
        return (x, y)

    def SetData(self, x, y, valKey, val):
        if self.ValidXY(x, y):
            self.data[x+y*self.width].SetVal(valKey, val)
            return True
        return False

    def AddData(self, x, y, valKey, val):
        if self.ValidXY(x, y):
            self.data[x+y*self.width].AddVal(valKey, val)
            return True
        return False

    def GetDistance(self, x1, y1, x2, y2):
        return ((x1-x2)**2 + (y1-y2)**2)**0.5

    def UpdateAttrTable(self, game):
        if game.goldCellNum <= 2:
            self.attrTable["golden"]["val"] = 2
        else:
            self.attrTable["golden"]["val"] = 1

        if game.uid == game.users[0].id:
            self.attrTable['base']['val'] = 4
        else:
            self.attrTable['base']['val'] = 2

    def EvalSpreadPattern(self, xx, yy, valKey, multi = 1):
        for x in range(xx - 2, xx + 3):
            for y in range(yy - 2, yy + 3):
                if self.ValidXY(x, y):
                    val = 1/((1 + self.GetDistance(x, y, xx, yy))**2)
                    self.AddData(x, y, valKey, val*multi)

    def EvalLocation(self, game, cell):
        midWidth  = game.width / 2.0
        midHeight = game.height / 2.0
        val = ((cell.x - midWidth)**2 + (cell.y - midHeight)**2)**0.5 / ((midWidth**2 + midHeight**2)**0.5)
        self.SetData(cell.x, cell.y, "location", val)

    # Pre: cell is golden
    def EvalGoldenCells(self, game, cell):
        self.EvalSpreadPattern(cell.x, cell.y, "golden")

    # Pre: cell is base
    def EvalBase(self, game, cell):
        baseUid = cell.owner
        selfCellNum = 0
        # if it's enemy's base
        if baseUid != game.uid:
            for c in game.GetAdjacentCells(cell.x, cell.y):
                if c.owner == baseUid:
                    selfCellNum += 1
                    self.AddData(c.x, c.y, "base", 0.25)
            if selfCellNum == 0:
                self.EvalSpreadPattern(cell.x, cell.y, "base")
                self.AddData(cell.x, cell.y, "base", 0.5)
            else:
                if cell.isBuilding:
                    self.EvalSpreadPattern(cell.x, cell.y, "base")
                    self.AddData(cell.x, cell.y, "base", 1)
                else:
                    # [1,2,3,4] for [2.5, 2, 1.5, 1]
                    self.EvalSpreadPattern(cell.x, cell.y, "base", 3-selfCellNum/2.0)
                    self.AddData(cell.x, cell.y, "base", -4)
        else:
            self.EvalSpreadPattern(cell.x, cell.y, "base")

    def EvalCost(self, game, cell):
        adjCellNums = 0
        for c in game.GetAdjacentCells(cell.x, cell.y):
            if c.owner == game.uid:
                adjCellNums += 1
        takeTime = cell.takeTime
        if (adjCellNums > 1):
            takeTime = takeTime * (1-((adjCellNums-1)*0.25))
        self.SetData(cell.x, cell.y, "cost", takeTime)

    def EvalCell(self, game, cell):
        self.EvalLocation(game, cell)
        if cell.cellType == "gold":
            self.EvalGoldenCells(game, cell)
        if cell.isBase:
            self.EvalBase(game, cell)
        self.EvalCost(game, cell)

    def GetEval(self, x, y):
        return self.data[x+self.width*y].TotalVal()

    def ExportJson(self, filePath):
        with open(filePath, 'w') as f:
            ret = {}
            ret['cells'] = []
            for d in self.data:
                ret['cells'].append(d.ToDict())
            json.dump(ret, f)

        
class Cell(colorfight.Cell):
    def __init__(self, cellData):
        colorfight.Cell.__init__(self, cellData)
    
class Game(colorfight.Game):
    def __init__(self):
        colorfight.Game.__init__(self)
        self.cellCache = None
        self.lastBuildBase = 0

    def GetCell(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            if self.cellCache[x+y*self.width] == None:
                c = Cell(self.data['cells'][x+y*self.width])
                return c
            else:
                return self.cellCache[x+y*self.width]
        return None

    def GetAdjacentCells(self, x, y):
        ret = []
        for d in [(-1,0), (1,0), (0,-1), (0,1)]:
            c = self.GetCell(x+d[0], y+d[1])
            if c != None:
                ret.append(c)
        return ret

    def FindBasePosition(self):
        best = (0, 0, -100)
        for x in range(self.width):
            for y in range(self.height):
                val = 0
                c = self.GetCell(x, y)
                if c.owner == self.uid:
                    for dx in range(-3, 4):
                        for dy in range(-3, 4):
                            c = self.GetCell(x+dx, y+dy)
                            if c == None:
                                val += 2
                            elif c.owner == self.uid:
                                val += 1
                                if c.isBase:
                                    val -= 10
                            elif c.owner != 0:
                                val -= 1

                    if val > best[2]:
                        best = (x, y, val)
        return best

    def Refresh(self):
        colorfight.Game.Refresh(self)
        self.cellCache = [None] * (self.width * self.height)
        self.evalMap = EvalMap(self.width, self.height)
        self.evalMap.UpdateAttrTable(self)
        for x in range(self.width):
            for y in range(self.height):
                c = self.GetCell(x, y)
                self.evalMap.EvalCell(self, c)


if __name__ == '__main__':
    # Instantiate a Game object.
    g = Game()
    g.Refresh()
    time1 = time.time()
    # You need to join the game using JoinGame(). 'MyAI' is the name of your
    # AI, you can change that to anything you want. This function will generate
    # a token file in the folder which preserves your identity so that you can
    # stop your AI and continue from the last time you quit. 
    # If there's a token and the token is valid, JoinGame() will continue. If
    # not, you will join as a new player.
    if g.JoinGame('MyAI'):
        # Put you logic in a while True loop so it will run forever until you 
        # manually stop the game
        while True:
            # Use a nested for loop to iterate through the cells on the map
            g.Refresh()
            g.evalMap.ExportJson('data.json')
            maxAtkCell = None
            for x in range(g.width):
                for y in range(g.height):
                    cell = g.GetCell(x,y)
                    if cell.owner == g.uid:
                        for atkCell in g.GetAdjacentCells(x,y):
                            if atkCell.owner != g.uid and atkCell.isTaking == False:
                                xx = atkCell.x
                                yy = atkCell.y
                                e = g.evalMap.GetEval(xx, yy)
                                if maxAtkCell == None:
                                    maxAtkCell = (xx, yy, e)
                                elif e > maxAtkCell[2]:
                                    maxAtkCell = (xx, yy, e)
            while True:
                success, err_code, err_msg = g.AttackCell(maxAtkCell[0], maxAtkCell[1])
                if err_code != 3:
                    break
                print success, err_code, err_msg

            if g.baseNum < 3 and g.gold > 60:
                baseX, baseY, baseVal = g.FindBasePosition()
                if g.lastBuildBase < time.time() - 30:
                    while True:
                        success, err_code, err_msg = g.BuildBase(baseX, baseY)
                        g.lastBuildBase = time.time()
                        print success, err_code, err_msg
                        if err_code != 3:
                            break
             
    else:
        print("Failed to join the game!")
