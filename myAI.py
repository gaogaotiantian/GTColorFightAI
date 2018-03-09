# You need to import colorfight for all the APIs
import API.colorfight as colorfight
import random
import json
import time
import threading
import Queue
from spreadrange import SpreadRange
from heapq import *
from API.colorfight import cellDataLock


class EvalPoint:
    def __init__(self, x = None, y = None, attrTable = None):
        self.vals = {}
        self.goldVal = 0
        self.x = x
        self.y = y
        self.attrTable = attrTable
        self.cost = 1
        self.rankBias = 1
        for attr in self.attrTable:
            self.vals[attr] = 0
    def SetVal(self, valKey, val):
        if valKey == "cost":
            self.cost = val
        elif valKey == "rankBias":
            self.rankBias = val
        else:
            self.vals[valKey] = val
    def AddVal(self, valKey, val):
        if valKey == "cost":
            self.cost += val
        elif valKey == "rankBias":
            self.rankBias += val
        else:
            if valKey not in self.vals:
                self.vals[valKey] = val
            else:
                self.vals[valKey] += val
    def GetVal(self, valKey):
        if valKey == "cost":
            return self.cost
        if valKey not in self.vals:
            return 0
        return self.vals[valKey]
    def KeyVal(self, keyList):
        ret = 0
        for k in keyList:
            ret = ret + self.vals[k]*self.attrTable[k]["val"]
        return ret

    def AtkVal(self):
        ret = 0
        for k in ["location", "golden", "base", "energy"]:
            ret = ret + self.vals[k]*self.attrTable[k]["val"]
        return ret
    def DefVal(self):
        ret = 0
        return self.vals['defense']
    def Cost(self):
        return self.cost
    def ToDict(self):
        ret = {"atkVal":self.AtkVal(), "defVal":self.DefVal(), "x":self.x, "y":self.y, "cost":self.cost}
        for k, v in self.vals.items():
            ret[k] = v*self.attrTable[k]['val']
        return ret

class EvalMap:
    def __init__(self, width, height, game):
        self.game = game
        self.width = width
        self.height = height
        self.killingMode = False
        self.dynamicAttr = ["base", "cost", "defense", "blast", "blastDef", "energy", "golden"]
        self.attrTable = {
            "location": {"val":1},
            "golden": {"val":1},
            "energy": {"val":1},
            "base":{"val":2},
            "defense":{"val":1},
            "blast":{"val":1},
            "blastDef":{"val":1}
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

    def GetEvalPoint(self, x, y):
        return self.data[x+y*self.width]

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
        if game.goldCellNum <= 2 and game.baseNum < 3:
            self.attrTable["golden"]["val"] = 4
        elif game.rank != 1:
            self.attrTable["golden"]["val"] = 3
        else:
            self.attrTable["golden"]["val"] = 2

        self.attrTable["energy"]["val"] = 0.2 / ((0.5 + game.energyCellNum) / (game.cellNum+1))

        if len(game.users) == 2:
            self.attrTable['base']['val'] = 4
        elif len(game.users) > 0 and game.rank == 1:
            if len(game.users) > 1:
                self.attrTable['base']['val'] = 3 + (game.users[0].cellNum - game.users[1].cellNum)/50
            else:
                self.attrTable['base']['val'] = 2
        else:
            self.attrTable['base']['val'] = 1.5
        if self.killingMode:
            self.attrTable['energy']['val'] *= 3
            self.attrTable['base']['val'] *= 1.5

    def EvalSpreadPattern(self, xx, yy, valKey, multi = 1, skipMid = False, evalRange = 6, stopOnSelf = False, stopDelay = 0, decreaseFactor = 2.0):
        stopDist = evalRange + 10
        for dx, dy in SpreadRange(0, evalRange+1):
            x = xx + dx
            y = yy + dy
            if self.ValidXY(x, y):
                if stopOnSelf:
                    if self.game.GetCell(x,y).owner == self.game.uid and stopDist > abs(dx) + abs(dy):
                        stopDist = abs(dx) + abs(dy)
                    if abs(dx) + abs(dy) > stopDist + stopDelay:
                        break
                if skipMid and x == xx and y == yy:
                    pass
                else:
                    val = 1/((1 + self.GetDistance(x, y, xx, yy)/decreaseFactor))
                    self.AddData(x, y, valKey, val*multi)
    def ClosestSelfCellDistance(self, game, cell, maxTry = 10):
        for dx, dy in SpreadRange(maxTry+1):
            x = cell.x + dx
            y = cell.y + dy
            if self.ValidXY(x, y):
                if game.GetCell(x, y).owner == game.uid:
                    return abs(dx) + abs(dy)
        return None

    def EvalLocation(self, game, cell):
        midWidth  = game.width / 2.0
        midHeight = game.height / 2.0
        val = 1+((cell.x - midWidth)**2 + (cell.y - midHeight)**2)**0.5 / ((midWidth**2 + midHeight**2)**0.5)
        self.SetData(cell.x, cell.y, "location", val)

    # Pre: cell is golden
    def EvalGoldenCells(self, game, cell):
        if cell.owner == game.uid:
            self.EvalSpreadPattern(cell.x, cell.y, "golden", evalRange = 3)
            self.EvalSpreadPattern(cell.x, cell.y, "blastDef", evalRange = 2, multi = self.attrTable['golden']['val'])
            self.AddData(cell.x, cell.y, "blastDef", self.attrTable['golden']['val'])
        else:
            selfDistance = self.ClosestSelfCellDistance(game, cell)
            if selfDistance != None:
                if self.killingMode == False:
                    self.EvalSpreadPattern(cell.x, cell.y, "golden", evalRange = selfDistance - 1)
                else:
                    self.EvalSpreadPattern(cell.x, cell.y, "golden", evalRange = selfDistance - 1, decreaseFactor = 3)
                self.AddData(cell.x, cell.y, "golden", 0.5)

    # Pre: cell is energy 
    def EvalEnergyCells(self, game, cell):
        if cell.owner == game.uid:
            self.EvalSpreadPattern(cell.x, cell.y, "energy", evalRange = 3, decreaseFactor = 3)
            self.EvalSpreadPattern(cell.x, cell.y, "blastDef", evalRange = 2, multi = self.attrTable['energy']['val'])
            self.AddData(cell.x, cell.y, "blastDef", self.attrTable['energy']['val'])
        else:
            selfDistance = self.ClosestSelfCellDistance(game, cell)
            if selfDistance != None:
                if self.killingMode == False:
                    self.EvalSpreadPattern(cell.x, cell.y, "energy", evalRange = selfDistance - 1)
                else:
                    self.EvalSpreadPattern(cell.x, cell.y, "energy", evalRange = selfDistance - 1, decreaseFactor = 5)
                self.AddData(cell.x, cell.y, "energy", 1)

    # Pre: cell is base
    def EvalBase(self, game, cell):
        baseUid = cell.owner
        selfCellNum = 0
        if baseUid != game.uid:
            # if it's enemy's base
            maxAdjCellTakeTime = 0
            for c in game.GetAdjacentCells(cell.x, cell.y):
                if c.owner == baseUid and (c.isTaking == False or (c.isTaking == True and c.attacker == baseUid)):
                    if not c.isBase:
                        selfCellNum += 1
                        if c.isTaking == True and c.attacker == baseUid:
                            maxAdjCellTakeTime = 60
                        elif c.takeTime > maxAdjCellTakeTime:
                            maxAdjCellTakeTime = c.takeTime
                    self.AddData(c.x, c.y, "base", 0.25)
            if selfCellNum == 0:
                # in this case, we can take this base directly
                enemyUser = game.GetUserById(cell.owner)
                if enemyUser == None:
                    print "Error! Can't find user"
                else:
                    # if the user has [1, 2, 3] bases, multi times [2, 1.5, 1]
                    multi = (1 + (3 - enemyUser.baseNum) / 2.0)
                    self.AddData(cell.x, cell.y, "base", 2*multi)
            else:
                if cell.isBuilding:
                    # If the base is being built, try to stop it
                    self.EvalSpreadPattern(cell.x, cell.y, "base", stopOnSelf = True)
                    self.AddData(cell.x, cell.y, "base", 1)
                else:
                    # If the base is under normal condition, the more owned cells
                    # it is adjacent to, the less urgent we need to attack it
                    # [1,2,3,4] for [2.5, 2, 1.5, 1]
                    multi = 3-selfCellNum/2.0
                    # We also want to consider the case where there is a nearby
                    # cell just renewed. We only consider the max take time for
                    # nearby cells, the long it takes, the less this base worth
                    # for us
                    multi = multi * 3.0 / maxAdjCellTakeTime
                    # We also need to consider how many bases does this user 
                    # have.
                    enemyUser = game.GetUserById(cell.owner)
                    if enemyUser == None:
                        print "Error! Can't find user"
                    else:
                        # if the user has [1, 2, 3] bases, multi times [2, 1.5, 1]
                        multi = multi * (1 + (3 - enemyUser.baseNum) / 2.0)
                    if self.killingMode == False:
                        self.EvalSpreadPattern(cell.x, cell.y, "base", multi = multi, skipMid = True, evalRange = 4, stopOnSelf = True, stopDelay = 1)
                    else:
                        self.EvalSpreadPattern(cell.x, cell.y, "base", multi = multi, skipMid = True, stopOnSelf = True, stopDelay = 1, decreaseFactor = 4)
                    self.AddData(cell.x, cell.y, "base", -multi)
        else:
            # if it's my base
            # if the I have [1, 2, 3] bases, multi times [2, 1.5, 1]
            multi = (1 + (3 - game.baseNum) / 2.0)
            self.EvalSpreadPattern(cell.x, cell.y, "base", evalRange = 4, multi = multi)
            self.EvalSpreadPattern(cell.x, cell.y, "blast", multi=2*multi, evalRange = 3)
            self.EvalSpreadPattern(cell.x, cell.y, "blastDef", evalRange = 2, multi = multi)
            # defense code here
            adjEnemyCellNum = 0
            for c in game.GetAdjacentCells(cell.x, cell.y):
                if c.owner != baseUid and c.owner != 0 and c.occupyTime > g.currTime - 12:
                    adjEnemyCellNum += 1
            if adjEnemyCellNum > 0:
                for c in game.GetAdjacentCells(cell.x, cell.y):
                    if c.owner == baseUid:
                        self.AddData(c.x, c.y, "defense", adjEnemyCellNum*(4-game.baseNum))

    def EvalCost(self, game, cell):
        if cell.isTaking:
            takeTime = 40
        else:
            adjCellNums = 0
            for c in game.GetAdjacentCells(cell.x, cell.y):
                if c.owner == game.uid:
                    adjCellNums += 1
            takeTime = cell.takeTime
            if (adjCellNums > 1):
                takeTime = takeTime * (1-((adjCellNums-1)*0.25))
        if takeTime <= 0:
            print "Error! Unexpected take time!"
            print takeTime
            print cell
            print adjCellNums
        self.SetData(cell.x, cell.y, "cost", takeTime)

    def EvalRankBias(self, game, cell):
        m = game.rankMap
        if cell.owner in m and m[cell.owner] < g.rank:
            # Here g.rank can't be 1
            self.SetData(cell.x, cell.y, "rankBias", 1+1/(g.rank-1))
        else:
            self.SetData(cell.x, cell.y, "rankBias", 1)

    def EvalCellDynamic(self, game, cell):
        self.EvalCost(game, cell)
        if cell.isBase:
            self.EvalBase(game, cell)
        if cell.cellType == "gold":
            self.EvalGoldenCells(game, cell)
        elif cell.cellType == "energy":
            self.EvalEnergyCells(game, cell)
        self.EvalRankBias(game, cell)

    def EvalCellStatic(self, game, cell):
        self.EvalLocation(game, cell)

    def ClearDynamic(self):
        for d in self.data:
            for attr in self.dynamicAttr:
                d.SetVal(attr, 0)

    def GetListEval(self, x, y, evalList):
        d = self.data[x+self.width*y]
        return d.KeyVal(evalList) * d.rankBias

    def GetAtkEval(self, x, y):
        d = self.data[x+self.width*y]
        hasEnemy = 1
        for cell in self.game.GetAdjacentCells(x, y):
            if cell.owner != 0 and cell.owner != self.game.uid:
                hasEnemy = 1.2
                break

        return d.AtkVal() * d.rankBias * hasEnemy

    def GetDefEval(self, x, y):
        d = self.data[x+self.width*y]
        return d.DefVal()

    def GetBlastDefEval(self, game, blastCellAxis):
        ret = 0.0
        for cellAxis in blastCellAxis:
            x = cellAxis[0]
            y = cellAxis[1]
            c = game.GetCell(x, y)
            if c != None and c.owner == game.uid and c.isTaking == False:
                nearEnemy = 0
                for dx, dy in SpreadRange(1,2):
                    cc = game.GetCell(x+dx, y+dy)
                    if cc != None and cc.owner != game.uid and cc.owner != 0 and game.currTime - cc.finishTime < 15:
                        nearEnemy = 1
                        break
                else:
                    for dx, dy in SpreadRange(2, 3):
                        cc = game.GetCell(x+dx, y+dy)
                        if cc != None and cc.owner != game.uid and cc.owner != 0 and game.currTime - cc.finishTime < 15:
                            nearEnemy = 0.5
                            break
                takeTime = c.takeTime
                multi = (33 / takeTime)/20 + 0.1
                ret += nearEnemy * multi * self.GetListEval(x, y, ["blastDef"]) * self.attrTable['blastDef']['val']
        return ret

    def GetBestBlastDefEval(self, game, x, y):
        result = []
        method = "horizontal"
        cellAxis = []
        for i in [-4,-3,-2,-1,0,1,2,3,4]:
            cellAxis.append((x+i, y))
        eh = self.GetBlastDefEval(game, cellAxis)
        result.append((eh, "horizontal"))

        cellAxis = []
        for i in [-4,-3,-2,-1,0,1,2,3,4]:
            cellAxis.append((x, y+i))
        ev = self.GetBlastDefEval(game, cellAxis)
        result.append((ev, "vertical"))

        cellAxis = []
        for i in range(-1, 2):
            for j in range(-1, 2):
                cellAxis.append((x+i, y+j))
        es = self.GetBlastDefEval(game, cellAxis)
        result.append((es, "square"))

        e, method = max(result)

        return e, method

    def GetBlastAtkEval(self, game, blastCellAxis):
        ret = 0.0
        realBlastCells = []
        for cellAxis in blastCellAxis:
            x = cellAxis[0]
            y = cellAxis[1]
            c = game.GetCell(x, y)
            if c != None and ((c.owner != 0 and c.owner != game.uid) or (c.isTaking and c.attacker != game.uid and c.attacker != 0)):
                if c.isBase:
                    if c.isBuilding:
                        ret += 3.0*self.attrTable['base']['val']
                    else:
                        for cc in game.GetAdjacentCells(x, y):
                            # if the base has an adjacent cell that can't be cleared
                            # by this blast, we give up
                            if cc.owner == c.owner and (cc.x, cc.y) not in blastCellAxis:
                                break
                        else:
                            # Here we can clear the base by this blast!
                            ret += 3.0*self.attrTable['base']['val']
                selfCells = 0
                for cc in game.GetAdjacentCells(x, y):
                    if cc.owner == game.uid:
                        selfCells += 1
                ret += (0.1+selfCells*0.1) * self.GetListEval(x, y, ["golden", "energy"]) + self.GetListEval(x, y, ["blast"])
                realBlastCells.append((x, y))
        return ret, realBlastCells


    def GetBestBlastAtkEval(self, game, x, y):
        result = []
        method = "horizontal"
        cellAxis = []
        for i in [-4,-3,-2,-1,1,2,3,4]:
            cellAxis.append((x+i, y))
        eh, realCells = self.GetBlastAtkEval(game, cellAxis)
        result.append((eh, realCells[:], "horizontal"))

        cellAxis = []
        for i in [-4,-3,-2,-1,1,2,3,4]:
            cellAxis.append((x, y+i))
        ev, realCells = self.GetBlastAtkEval(game, cellAxis)
        result.append((ev, realCells[:], "vertical"))

        cellAxis = []
        for i in range(-1, 2):
            for j in range(-1, 2):
                if i != 0 or j != 0:
                    cellAxis.append((x+i, y+j))
        es, realCells = self.GetBlastAtkEval(game, cellAxis)
        result.append((es, realCells[:], "square"))

        e, cells, method = max(result)

        return e, method, cells

    def GetDefCost(self, game, x, y):
        d = self.data[x+self.width*y]
        assert(d.Cost() > 0)
        cost = d.Cost() * (1 /(1 + game.energy / 200))
        return cost

    def GetAtkCost(self, game, x, y):
        d = self.data[x+self.width*y]
        c = game.GetCell(x, y)
        cost = d.Cost() * (1 /(1 + game.energy / 200))
        if c.owner != 0 and c.owner != game.uid:
            cost += self.GetEnergyCost(game, game.energy*0.05)
        return cost

    def GetEnergyCost(self, game, energyCost):
        if game.energyCellNum == 0:
            return 60
        if energyCost < 0:
            return 0

        recoverTime = (100 - game.energy + energyCost) / (0.5 * game.energyCellNum)
        
        oldTime = 2.0/3
        newTime = 1/(1+(game.energy-energyCost)/200.0)
        # old = takeTime * oldTime
        # new ~= takeTime * ((oldTime + newTime)/2)
        # diff = takeTime *((oldTime + newTime)/2 - oldTime)
        #      = takeTime * ((newTime - oldTime)/2)
        lost = (newTime - oldTime) / 2

        return recoverTime * lost
    
    def GetGoldCost(self, game, goldCost):
        if game.goldCellNum == 0:
            return 60
        if game.baseNum == 3:
            return 2 + (100 - game.gold) * goldCost / (100 * game.goldCellNum)
        return 60

    def GetBoostCost(self, game, x, y):
        d = self.data[x+self.width*y]
        takeTime = max(1, d.Cost()*0.1) 
        return takeTime + self.GetEnergyCost(game, 10 - 0.5*takeTime*game.energyCellNum)

    def GetBlastAtkCost(self, game):
        return 1 + self.GetEnergyCost(game, 30 - 0.5*game.energyCellNum)

    def GetBlastDefCost(self, game):
        return 2 + self.GetGoldCost(game, 40 - 1*game.goldCellNum)

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
        self.cellCache = None
        self.lastBuildBase = 0
        self.lastBlastCells = None
        self.evalMap = None
        self.rank = 0
        self.rankMap = {}
        colorfight.Game.__init__(self)

    def GetUserById(self, uid):
        for u in self.users:
            if u.id == uid:
                return u
        return None

    def GetCell(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            if self.cellCache[x+y*self.width] == None:
                cellDataLock.acquire()
                c = Cell(self.data['cells'][x+y*self.width])
                cellDataLock.release()
                self.cellCache[x+y*self.width] = c
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

    def ChangeCellOwner(self, dataList):
        if self.data != None:
            cellDataLock.acquire()
            for x, y, o in dataList:
                if 0 <= x < self.width and 0 <= y < self.height:
                    if o == 0:
                        # This is a blast
                        if self.data['cells'][x + y*self.width]['o'] != self.uid:
                            self.data['cells'][x + y*self.width]['o'] = o
                            self.data['cells'][x + y*self.width]['c'] = 0
                            self.data['cells'][x + y*self.width]['t'] = 2
                            if self.data['cells'][x + y*self.width]['b'] == 'base':
                                self.data['cells'][x + y*self.width]['b'] = 'empty'
                    else:
                        self.data['cells'][x + y*self.width]['o'] = o
                        self.data['cells'][x + y*self.width]['c'] = 0
                        self.data['cells'][x + y*self.width]['t'] = 30
                        if self.data['cells'][x + y*self.width]['b'] == 'base':
                            self.data['cells'][x + y*self.width]['b'] = 'empty'
                    self.cellCache[x+y*self.width] = None
            cellDataLock.release()

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
                                val += 0.5 / (1+abs(dx)+abs(dy))
                            elif c.owner == self.uid:
                                val += 1.0 / (1+abs(dx)+abs(dy))
                                if c.isBase:
                                    val -= 4.0 / (1+abs(dx)+abs(dy))
                            elif c.owner == 0:
                                val += 0.75 / (1+abs(dx)+abs(dy))
                            else:
                                val -= 1 / (1+abs(dx)+abs(dy))

                    if val > best[2]:
                        best = (x, y, val)
        return best

    def Refresh(self):
        lastGameId = self.gameId
        evaluateLock.acquire()
        ret = colorfight.Game.Refresh(self)
        evaluateLock.release()
        self.rank = 0
        for idx, u in enumerate(self.users):
            self.rankMap[u.id] = idx + 1
            if u.id == self.uid:
                self.rank = idx + 1
        if self.gameId != lastGameId:
            return False
        self.cellCache = [None] * (self.width * self.height)
        return ret

    def Evaluate(self, force = False, wait = True):
        if evaluateLock.acquire(wait):
            if self.evalMap == None or force:
                self.evalMap = EvalMap(self.width, self.height, game = self)
                for x in range(self.width):
                    for y in range(self.height):
                        c = self.GetCell(x, y)
                        self.evalMap.EvalCellStatic(self, c)

            if self.energyCellNum >= 10 and self.rank == 1:
                self.evalMap.killingMode = True
                print "Killing Mode on!"
            else:
                self.evalMap.killingMode = False
            self.evalMap.ClearDynamic()
            self.evalMap.UpdateAttrTable(self)
            for x in range(self.width):
                for y in range(self.height):
                    c = self.GetCell(x, y)
                    self.evalMap.EvalCellDynamic(self, c)
            evaluateLock.release()

    def RefreshActions(self, actionQueue, wait = True):
        if evaluateLock.acquire(wait):
            actionTaskList = ActionTaskList()
            blastAtkCost = self.evalMap.GetBlastAtkCost(g)
            blastDefCost = self.evalMap.GetBlastDefCost(g)
            print "Refreshing actions"
            for x in range(self.width):
                for y in range(self.height):
                    cell = self.GetCell(x,y)
                    if cell.owner == self.uid or (cell.isTaking and cell.attacker == self.uid) :
                        if cell.owner == self.uid:
                            # Normal defense
                            e = self.evalMap.GetDefEval(x, y)
                            ec1 = e / self.evalMap.GetDefCost(self, x, y)
                            actionTask = ActionTask(x, y, val=ec1, method='attack', boost=False)
                            actionTaskList.EvalAction(actionTask)

                        for atkCell in self.GetAdjacentCells(x,y):
                            if atkCell.owner != self.uid and atkCell.isTaking == False:
                                xx = atkCell.x
                                yy = atkCell.y
                                e = self.evalMap.GetAtkEval(xx, yy) 
                                ec1 = e / self.evalMap.GetAtkCost(self, xx, yy)

                                # Normal Attack
                                actionTask = ActionTask(xx, yy, val=ec1, method='attack', boost=False)
                                actionTaskList.EvalAction(actionTask)

                                boostCost = self.evalMap.GetBoostCost(self, x, y)
                                # Boost Attack
                                ec2 = e / boostCost
                                if self.energy >= 10:
                                    actionTask = ActionTask(xx, yy, val=ec2, method='attack', boost=True)
                                    actionTaskList.EvalAction(actionTask)

                        e, direction, blastCells = self.evalMap.GetBestBlastAtkEval(self, x, y)
                        ecba = e / blastAtkCost
                        if self.energy >= 30:
                            actionTask = ActionTask(x, y, val=ecba, method='blast', direction=direction, blastCells=blastCells[:])
                            actionTaskList.EvalAction(actionTask)

                        e, direction = self.evalMap.GetBestBlastDefEval(self, x, y)
                        ecbd = e/blastDefCost
                        if self.gold >= 40:
                            actionTask = ActionTask(x, y, val=ecbd, method='blastDef', direction=direction)
                            actionTaskList.EvalAction(actionTask)

            actionTaskList.ClearAndPutInQueue(actionQueue)
            print actionTaskList
            evaluateLock.release()
        
class ActionTaskList:
    def __init__(self):
        self.heap = {}
        self.size = {}
        self.heap['attack'] = []
        self.size['attack'] = 9
        self.heap['blast'] = []
        self.size['blast'] = 1
        self.heap['blastDef'] = []
        self.size['blastDef'] = 1
        self.heapPrint = []
    
    def EvalAction(self, action):
        if action.method not in self.heap:
            return
        method = action.method

        for data in self.heap[method]:
            # check replicate
            if data == action:
                return
        if len(self.heap[method]) < self.size[method]:
            heappush(self.heap[method], action)
        else:
            heappushpop(self.heap[method], action)

    def ClearAndPutInQueue(self, q):
        lst = []
        while self.heap['blast']:
            heappush(self.heap['attack'], heappop(self.heap['blast']))
        while self.heap['blastDef']:
            heappush(self.heap['attack'], heappop(self.heap['blastDef']))
        while self.heap['attack']:
            lst.append(heappop(self.heap['attack']))
        self.heapPrint = lst[:]
        actionQueueLock.acquire()
        while not q.empty():
            q.get()
        for d in lst[::-1]:
            q.put(d)
        actionQueueLock.release()

    def __repr__(self):
        ret = ""
        for action in self.heapPrint:
            ret = ret + (str(action) + '\n')
        return ret

class ActionTask:
    def __init__(self, x, y, val = 0, method = None ,boost = False, direction = "", blastCells = []):
        self.x = x
        self.y = y
        self.val = val
        self.method = method
        self.boost = boost
        self.direction = direction
        self.blastCells = blastCells
    def __cmp__(self, other):
        if type(other) != type(self):
            return 1
        if self.x == other.x and self.y == other.y and self.method == other.method:
            return 0
        return cmp(self.val, other.val)
    def SameAction(self, other):
        if type(self) != type(other):
            return False
        if self.method == 'blast' and other.method == 'blast':
            if abs(self.x - other.x) + abs(self.y - other.y) <= 8:
                return True
        if self.method == 'blast' and other.method == 'attack':
            if (other.x, other.y) in self.blastCells:
                return True
        return (self.x == other.x and self.y == other.y and self.method == other.method)
    def __repr__(self):
        return "x:{}, y:{}, val:{}, method:{}, boost:{}".format(self.x, self.y, self.val, self.method, self.boost)

class ActionThread(threading.Thread):
    def __init__(self, game, actionQueue, refreshQueue):
        threading.Thread.__init__(self)
        self.game = game
        self.actionQueue = actionQueue
        self.refreshQueue = refreshQueue
        self.lastActions = []

    def run(self):
        while True:
            actionQueueLock.acquire()
            if not self.actionQueue.empty():
                action = self.actionQueue.get()
                actionQueueLock.release()
            else:
                actionQueueLock.release()
                action = None
                time.sleep(0.25)

            if action != None:
                # keep a last action list about 3-5 size long
                # make sure do not do the same thing
                if len(self.lastActions) >= 5:
                    self.lastActions = self.lastActions[-3:]
                for lastAction in self.lastActions:
                    if action.SameAction(lastAction):
                        break
                else:
                    didAction = False
                    while didAction == False:
                        print "Check Action"
                        if action.method == 'attack':
                            success, err_code, err_msg = self.game.AttackCell(action.x, action.y, boost = action.boost)
                            if success:
                                self.game.ChangeCellOwner([(action.x, action.y, self.game.uid)])
                                self.lastActions.append(action)
                                print "============= Attack ==============", action.x, action.y
                                didAction = True

                        elif action.method == 'blast':
                            success, err_code, err_msg = self.game.Blast(action.x, action.y, action.direction, 'attack')
                            # Update that cell forehead 
                            if success:
                                dataList = []
                                for cell in action.blastCells:
                                    dataList.append((cell[0], cell[1], 0))
                                self.game.ChangeCellOwner(dataList)
                                self.lastActions.append(action)
                                didAction = True
                                print "================ Blast =================", action.x, action.y

                        elif action.method == 'blastDef':
                            success, err_code, err_msg = self.game.Blast(action.x, action.y, action.direction, 'defense')
                            # Update that cell forehead 
                            if success:
                                dataList = []
                                self.lastActions.append(action)
                                didAction = True
                                print "================ Blast Defense =================", action.x, action.y

                        if not didAction:
                            actionQueueLock.acquire()
                            if not self.actionQueue.empty():
                                actionNow = self.actionQueue.get()
                                actionQueueLock.release()
                            else:
                                actionQueueLock.release()
                                actionNow = None
                            if actionNow and actionNow.val > action.val:
                                for lastAction in self.lastActions:
                                    if actionNow.SameAction(lastAction):
                                        break
                                else:
                                    action = actionNow

if __name__ == '__main__':
    # Instantiate a Game object.
    refreshQueue = Queue.Queue()
    actionQueue  = Queue.Queue()
    actionQueueLock = threading.Lock()
    evaluateLock    = threading.Lock()
    g = Game()
    g.Refresh()
    actionThread = ActionThread(g, actionQueue, refreshQueue)
    actionThread.daemon = True
    actionThread.start()
    # You need to join the game using JoinGame(). 'MyAI' is the name of your
    # AI, you can change that to anything you want. This function will generate
    # a token file in the folder which preserves your identity so that you can
    # stop your AI and continue from the last time you quit. 
    # If there's a token and the token is valid, JoinGame() will continue. If
    # not, you will join as a new player.
    while True:
        if g.joinEndTime != 0 and len(g.users) > 1:
            g.JoinGame('MyAI')
        else:
            print "Rest for 30 seconds"
            time.sleep(30)
            g.Refresh()
            continue
        g.Evaluate(force = True)
        boostCost = 0
        while True:
            # Use a nested for loop to iterate through the cells on the map
            time1 = time.time()
            if not g.Refresh():
                print "Refresh failed!"
                break;
            if len(g.users) < 2 or g.rank == 0:
                print "Died or no enough users"
                break
            time2 = time.time()
            g.Evaluate()
            time3 = time.time()
            # Update the attacked cell after refresh
            g.evalMap.ExportJson('data.json')
            time4 = time.time()
            g.RefreshActions(actionQueue)
            time5 = time.time()
            # Build base first because it does not take CD
            if g.baseNum < 3 and g.gold > 60:
                baseX, baseY, baseVal = g.FindBasePosition()
                if g.lastBuildBase < time.time() - 30:
                    while True:
                        success, err_code, err_msg = g.BuildBase(baseX, baseY)
                        g.lastBuildBase = time.time()
                        print success, err_code, err_msg
                        if err_code != 3:
                            break

            g.lastBlastCells = None

            time6 = time.time()
            print "Refresh takes {}\nEvaluate takes{}\nExport takes{}\nFind taks{}\nAct takes {}\n".format(time2-time1, time3-time2, time4-time3, time5-time4, time6-time5)
             
    else:
        print("Failed to join the game!")
