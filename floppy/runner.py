"""
Module implementing a program for executing a Floppy graph.
The program can be called from the Floppy editor but will run independently from the calling process.
Communication between the editor and the runner is realized via Sockets.
The runner will report its status to the editor and the editor is able to send commands to the runner.
"""

from threading import Thread, Lock
import time
from queue import Queue
from socket import AF_INET, SOCK_STREAM, socket, SHUT_RDWR, timeout, SHUT_RDWR, SO_REUSEADDR, SOL_SOCKET
import random
import json



host = '127.0.0.1'
port = 7236

updatePort = 7237

xLock = Lock()


class Runner(object):

    def __init__(self):
        self.conn = None
        self.idMap = None
        self.nextNodePointer = None
        self.currentNodePointer = None
        self.lastNodePointer = None
        self.graphData = {}
        self.cmdQueue = Queue(1)
        self.listener = Listener(self)
        self.executionThread = ExecutionThread(self.cmdQueue, self)

        self.updateSocket = socket(AF_INET, SOCK_STREAM)
        self.updateSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.updateSocket.bind((host, updatePort))
        self.updateSocket.listen(1)
        self.conn, self.clientAddress = None, None




    def resetPointers(self):
        self.nextNodePointer = None
        self.currentNodePointer = None
        self.lastNodePointer = None

    def recvall(self, sock, n):
        # Helper function to recv n bytes or return None if EOF is hit
        data = b''
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data += packet

        return data

    def updateGraph(self, _):
        if not self.conn:
            self.conn , address = self.updateSocket.accept()
        import struct

        raw_msglen = self.recvall(self.conn, 4)
        if not raw_msglen:
            return None
        msglen = struct.unpack('>I', raw_msglen)[0]
        # Read the message data
        data = self.recvall(self.conn, msglen).decode('utf-8')
        data = json.loads(data)

        self.graphData = data
        xLock.acquire()
        if not self.cmdQueue.empty():
            self.cmdQueue.get()
        self.cmdQueue.put(ExecutionThread.updateGraph)
        xLock.release()

    def pause(self):
        xLock.acquire()
        if not self.cmdQueue.empty():
            self.cmdQueue.get()
        self.cmdQueue.put(ExecutionThread.pause)
        xLock.release()

    def kill(self):
        self.updateSocket.close()
        xLock.acquire()
        if not self.cmdQueue.empty():
            self.cmdQueue.get()
        self.cmdQueue.put(ExecutionThread.kill)
        xLock.release()

    def unpause(self):
        xLock.acquire()
        if not self.cmdQueue.empty():
            self.cmdQueue.get()
        self.cmdQueue.put(ExecutionThread.unpause)
        xLock.release()

    def goto(self, nextID):
        self.nextNodePointer = nextID

    def step(self):
        xLock.acquire()
        if not self.cmdQueue.empty():
            self.cmdQueue.get()
        self.cmdQueue.put(ExecutionThread.step)
        xLock.release()

    def sendStatus(self, nodeID):
        nodeID = self.idMap[nodeID]
        self.conn.send(('#'+str(nodeID)).encode('utf-8'))


class ExecutionThread(Thread):
    def __init__(self, cmdQueue, master):
        self.graph = None
        self.master = master
        self.paused = True
        self.alive = True
        self.cmdQueue = cmdQueue
        super(ExecutionThread, self).__init__()
        # self.updateGraph()
        self.start()


    def run(self):
        while self.alive:
            xLock.acquire()
            cmd = None
            if not self.cmdQueue.empty():
                cmd = self.cmdQueue.get()
            xLock.release()
            # print(cmd)
            if cmd:
                cmd(self)
            if self.paused:
                print('Sleeping')
                time.sleep(1)
                continue
            if self.alive and self.graph:

                # print(self.graph.nodes)
                #print('Doing stuff.')
                self.executeGraphStep()
            else:
                time.sleep(.5)
        print('That\'s it. I\'m dead.')

    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False

    def kill(self):
        self.alive = False

    def step(self):
        print('Stepping up.')
        self.executeGraphStep()

    def updateGraph(self):
        from floppy.graph import Graph
        self.graph = Graph()
        # print(type(self.master.graph))
        idMap = self.graph.loadDict(self.master.graphData)
        self.master.idMap = {value:key for key, value in idMap.items()}
        #self.resetPointers()

    def executeGraphStep(self):
        if self.master.nextNodePointer:
            print(self.master.nextNodePointer, self.graph.nodes.keys())
            nextNode = self.graph.nodes[self.master.nextNodePointer]
            self.master.nextNodePointer = None
            if nextNode.check():
                nextNode.run()
                nextNode.notify()
                self.master.sendStatus(nextNode.ID)
        else:
            running = False
            for node in self.graph.nodes.values():
                checked = node.check()
                running = checked if not running else True
                if checked:
                    node.run()
                    # raise RuntimeError('Uncaught exception while executing node {}.'.format(node))
                    node.notify()
                    self.master.sendStatus(node.ID)
                    break
            if not running:
                print('Nothing to do here @ {}'.format(time.time()))
                time.sleep(.5)

    def execute(self):
        """
        Execute the Graph instance.

        First, the execution loop will set itself up to terminate after the first iteration.
        Next, every node is given the chance to run if all prerequisites are met.
        If a node is executed, the loop termination criterion will be reset to allow an additional iteration over all
        nodes.
        If no node is execute during one iteration, the termination criterion will not be reset and the execution loop
        terminates.
        :return:
        """
        return self.testRun()
        running = True
        i = 0
        while running:
            i += 1
            print('\nExecuting iteration {}.'.format(i))
            running = False
            for node in self.nodes.values():
                checked = node.check()
                running = checked if not running else True
                if checked:
                    node.run()
                    # raise RuntimeError('Uncaught exception while executing node {}.'.format(node))
                    node.notify()






class Listener(Thread):
    def __init__(self, master):
        Thread.__init__(self)
        self.alive = True
        self.listenSocket = socket(AF_INET, SOCK_STREAM)
        self.listenSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.listenSocket.bind((host, port))
        self.listenSocket.listen(5)
        self.master = master
        self.daemon = True
        self.start()

    def kill(self):
        self.alive = False
        time.sleep(.1)
        self.listenSocket.shutdown(SHUT_RDWR)


    def run(self):
        while self.alive:
            try:
                cSocket, address = self.listenSocket.accept()
            except OSError:
                continue
            if str(address[0]) == '127.0.0.1':
                CommandProcessor(cSocket, address, self.master, self)



class CommandProcessor(Thread):
    def __init__(self, cSocket, Adress, master, listener):
        super(CommandProcessor, self).__init__()
        self.master = master
        self.cSocket = cSocket
        self.listener = listener
        self.daemon = True
        self.start()

    def run(self):
        while True:
            message = self.cSocket.recv(1024).decode()
            if message:
                if message == 'KILL':
                    # print('Killing myself')
                    self.cSocket.send('Runner is terminating.'.encode())
                    self.listener.kill()
                    self.master.kill()
                    break
                elif message == 'PAUSE':
                    self.cSocket.send('Runner is pausing.'.encode())
                    self.master.pause()
                    break
                elif message == 'UNPAUSE':
                    self.cSocket.send('Runner is unpausing.'.encode())
                    self.master.unpause()
                    break
                elif message == 'UPDATE':
                    self.cSocket.send('Runner is updating.'.encode())
                    self.master.updateGraph('')
                    break
                elif message.startswith('GOTO'):
                    nextID = int(message[4:])
                    self.cSocket.send('Runner jumping to node {}.'.format(nextID).encode())
                    self.master.goto(nextID)
                elif message == 'STEP':
                    self.cSocket.send('Runner is performing one step.'.encode())
                    self.master.step()
                else:
                    self.cSocket.send('Command \'{}\' not understood.'.format(message).encode())
                    break



# from socket import AF_INET, SOCK_STREAM, socket


def terminate(clientSocket):
    message = 'Kill'
    clientSocket.send(message.encode())
    print('Kill command sent.')

    answer = clientSocket.recv(1024).decode()

    print(answer)


def sendCommand(cmd):
    # global clientSocket
    clientSocket = socket(AF_INET, SOCK_STREAM)
    clientSocket.settimeout(5.)

    host = '127.0.0.1'
    port = 7236

    clientSocket.connect((host, port))
    clientSocket.send(cmd.encode())
    print('Sent {} command'.format(cmd))
    # terminate(clientSocket)
    try:
        answer = clientSocket.recv(1024).decode()
        print(answer)
    except timeout:
        print('Runner did not answer command \'{}\''.format(cmd))


    clientSocket.close()

def spawnRunner():
    pass

if __name__ == '__main__':
    r = Runner()
    # input()
    # r.pause()
    # input()
    # r.unpause()
    # input()
    # r.updateGraph('')
    # input()
    # r.kill()
    # input()
    # sendCommand()


    # while True:
    #     time.sleep(1)
    #     sendCommand('KILL')
    #     break
    while True:
        cmd = str(input())
        print(cmd)
        if cmd == 'x':
            sendCommand('KILL')
            exit()
        sendCommand(cmd)