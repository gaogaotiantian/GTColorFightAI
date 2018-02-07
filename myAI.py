# You need to import colorfight for all the APIs
import API.colorfight as colorfight
import random
import json
class EvalPoint:
    def __init__(self, x = None, y = None):
        self.vals = {}
        self.goldVal = 0
        self.x = x
        self.y = y
        self.attrTable = {
            "location": {"val":3},
            "golden": {"val":1}
        }
    def SetVal(self, valKey, val):
        self.vals[valKey] = val
    def AddVal(self, valKey, val):
        if valKey not in self.vals:
            self.vals[valKey] = val
        else:
            self.vals[valKey] += val
    def GetVal(self, valKey):
        return self.vals[valKey]
    def TotalVal(self):
        ret = 0
        for k, v in self.vals.items():
            ret = ret + v*self.attrTable[k]["val"]
        return ret


class EvalMap:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.data = [None] * (width*height)
        for i in range(width * height):
            x, y = self.IndexToXY(i)
            self.data[i] = EvalPoint(x, y)

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

    def EvalLocation(self, game, cell):
        midWidth  = game.width / 2.0
        midHeight = game.height / 2.0
        val = ((cell.x - midWidth)**2 + (cell.y - midHeight)**2)**0.5 / ((midWidth**2 + midHeight**2)**0.5)
        self.SetData(cell.x, cell.y, "location", val)

    # Pre: cell is golden
    def EvalGoldenCells(self, game, cell):
        for x in range(cell.x - 2, cell.x + 3):
            for y in range(cell.y - 2, cell.y + 3):
                if self.ValidXY(x, y):
                    val = 1/((1 + self.GetDistance(x, y, cell.x, cell.y))**2)
                    self.AddData(x, y, "golden", val)


    def EvalCell(self, game, cell):
        self.EvalLocation(game, cell)
        self.EvalGoldenCells(game, cell)

    def ExportJson(self, filePath):
        with open(filePath, 'w') as f:
            ret = {}
            ret['cells'] = []
            for d in self.data:
                ret['cells'].append({"val":d.TotalVal(), "x":d.x, "y":d.y, "location":d.GetVal('location'), "golden":d.GetVal('golden')})
            json.dump(ret, f)

        
class Cell(colorfight.Cell):
    pass
    
class Game(colorfight.Game):
    def __init__(self):
        colorfight.Game.__init__(self)
        self.cellCache = None

    def GetCell(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            if self.cellCache[x+y*self.width] == None:
                c = Cell(self.data['cells'][x+y*self.width])
                return c
            else:
                return self.cellCache[x+y*self.width]
        return None
    def Refresh(self):
        colorfight.Game.Refresh(self)
        self.cellCache = [None] * (self.width * self.height)

if __name__ == '__main__':
    # Instantiate a Game object.
    g = Game()
    g.Refresh()
    evalMap = EvalMap(g.width, g.height)
    # You need to join the game using JoinGame(). 'MyAI' is the name of your
    # AI, you can change that to anything you want. This function will generate
    # a token file in the folder which preserves your identity so that you can
    # stop your AI and continue from the last time you quit. 
    # If there's a token and the token is valid, JoinGame() will continue. If
    # not, you will join as a new player.
    if g.JoinGame('Voldemort'):
        # Put you logic in a while True loop so it will run forever until you 
        # manually stop the game
        while True:
            # Use a nested for loop to iterate through the cells on the map
            g.Refresh()

            for x in range(g.width):
                for y in range(g.height):
                    # Get a cell
                    c = g.GetCell(x,y)
                    evalMap.EvalCell(g, c)
            evalMap.ExportJson('data.json')
            break
    else:
        print("Failed to join the game!")
