from __future__ import print_function
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from collections import namedtuple
from sendgcode import GCodeSender
import sys
import time
import threading
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'Idontcareaboutsecurityinthisapp'
socketio = SocketIO(app)
sids = set()

bufferData = threading.Event()
alive = True
buffer = []
BUFFER_GCODE = 'g'
BUFFER_CALLBACK = 'c'
BUFFER_MESSAGE = 'm'
BUFFER_MOVE_XY = 'xy'
BUFFER_MOVE_Z = 'z'

# positions in mm

home = (28.641,220.647,10)

Tool = namedtuple('Tool', ['x','y','wiggleAxis','wiggleDistance','wiggleIterations'])
Rect = namedtuple('Rect', ['x0','y0','width','height'])

def RTool(x0,y0,w,h):
    return Tool(x0+w/2,y0+h/2,w,h)
    
downZ = 0
upZ = 10
stepsPerMM = 17.78    
colorVerticalSpacing = 25.564
color0Y = 176.911
colorX = 15.094

tools = { "water0": Tool(8.659+55.269/2,169.548+55.269/2,'y', 0.3, 2),
          "water1": Tool(8.659+55.269/2,97.606+55.269/2,'y', 0.3, 2),
          "water2": Tool(8.659+55.269/2,25.663+55.269/2,'y', 0.3, 2),
          "color0": Tool(colorX, color0Y-colorVerticalSpacing*0, 'xy', 17, 4),
          "color1": Tool(colorX, color0Y-colorVerticalSpacing*1, 'xy', 17, 4),
          "color2": Tool(colorX, color0Y-colorVerticalSpacing*2, 'xy', 17, 4),
          "color3": Tool(colorX, color0Y-colorVerticalSpacing*3, 'xy', 17, 4),
          "color4": Tool(colorX, color0Y-colorVerticalSpacing*4, 'xy', 17, 4),
          "color5": Tool(colorX, color0Y-colorVerticalSpacing*5, 'xy', 17, 4),
          "color6": Tool(colorX, color0Y-colorVerticalSpacing*6, 'xy', 17, 4),
          "color7": Tool(colorX, color0Y-colorVerticalSpacing*7, 'xy', 17, 4)
          }
          
canvas = Rect(104.81, 6.116, 286.250, 214.812)

penHeight = 1 # 0=up, 1=down
penX = 0
penY = 0
servoHeight = 0
currentTool = "red"
lastDuration = 0
distanceCounter = 0
paused = False
    
def getTimestamp():
    # TODO: worry about locale
    return time.strftime("%a %b %d %Y %X %Z")

def getPositionXSteps():
    return int(0.5+(penX - home[0]) * stepsPerMM)

def getPositionYSteps():
    return int(0.5+(home[1] - penY) * stepsPerMM)

def getPenData():
    return { 'x': getPositionXSteps(), 'y': getPositionYSteps(), 'state':1, 'height': servoHeight, 
             'power': 0, 'tool': currentTool, 'lastDuration': lastDuration,
             distanceCounter: distanceCounter, 'simulation': 0 }

@socketio.on('connect')
def chat_connect():
    print ('socket.io connected',request.sid,request.namespace)
    sids.add(request.sid)
    myEmit('pen update', getPenData())
    bufferUpdate()

@socketio.on('disconnect')
def chat_disconnect():
    sids.remove(request.sid)
    print ("Client disconnected")
    
def myEmit(m, d):
    for sid in sids:
        emit(m, d, room=sid, namespace='/')

@socketio.on('broadcast')
def chat_broadcast(message):
    print ("test")
    emit("chat", {'data': message['data']})
    
@socketio.on('message')
def handle_message(message):
    print('received message: ' + message)

def moveXY(xy):
    addBuffer(BUFFER_MOVE_XY, xy)
    
def moveZ(z):
    addBuffer(BUFFER_MOVE_Z, z)
    
def setTool(tool):
    global currentTool
    print('TODO tool: ' + tool)
    currentTool = tool
    
def clearBuffer():
    buffer = []
    bufferUpdate()
    return jsonify( { 'status': 'buffer cleared' } )

@app.route('/')
def index():
    return "Hello, World!"
    
@app.route('/v1/tools', methods=['GET'])
def handle_tools_GET():
    return jsonify({'tools': list(sort(tools.keys()))})

@app.route('/v1/tools/<tool>', methods=['PUT'])
def handle_tools_PUT(tool):
    if tool in tools:
        setTool(tool)
        return jsonify({'status': 'Tool changed to '+tool})

@app.route('/v1/pen', methods=['GET','PUT','DELETE'])
def handle_pen():
    if request.method == 'GET':
        return jsonify(getPenData())
    elif request.method == 'DELETE':
        moveXY(home)
        return jsonify(getPenData())
    elif request.method == 'PUT':
        try:
            x = request.json['x']
            y = request.json['y']
            moveXY( ( canvas.x0 + canvas.width * x, canvas.y0 + canvas.height * (1.-y) ) )
            return jsonify(getPenData())
        except KeyError:
            try:
                if request.json['resetCounter']:
                    distanceCounter = 0
                return jsonify(getPenData())
            except KeyError:
                state = request.json['state']
                if state == 'wash':
                    state = 1.2
                elif state == 'wipe':
                    state = 0.9
                elif state == 'paint':
                    state = 1.0 
                elif state == 'up':
                    state = 0.0
                else:
                    try:
                        state = float(state)
                        if state < 0:
                            state = 0.
                        elif state > 1:
                            state = 1.
                    except:
                        return jsonify(getPenData())
                moveZ( state * downZ + (1-state) * upZ )
                return jsonify(getPenData())
    else:
        print('pen request:', request.json)
        return jsonify(getPenData())
    

@app.route('/v1/buffer', methods=['GET','POST','PUT','DELETE'])
def handle_buffer():
    def getData():
        return jsonify({'running': False, 'paused': paused, 'count': len(buffer), 'buffer': buffer})
    if request.method == 'DELETE':
        return clearBuffer()
    elif request.method == 'GET':
        return getData()
    elif request.method == 'PUT':
        paused = request.json.get('paused', False)
        print('paused',paused)
        bufferData.set()
        bufferUpdate()
        return getData()
    elif request.method == 'POST':
        msg = request.json.get('message',None)
        if msg:
            addBuffer(BUFFER_MESSAGE,msg)
        cb = request.json.get('callback',None)
        if cb:
            addBuffer(BUFFER_CALLBACK,cb)
        return jsonify({'status': "Message added to buffer"})

def addBuffer(type,data):
    print("adding", (type,data))
    buffer.append((type,data))
    bufferData.set()

outXY = home
outZ = upZ

def sendBufferLine():
    if not buffer:
        return
    data = buffer.pop(0)
    print("processing",data)
    if data[0] == BUFFER_CALLBACK:
        print("Callback update:", data[1])
        myEmit('callback update', {'name': data[1], 'timestamp': getTimestamp() })
    elif data[0] == BUFFER_MESSAGE:
        print("Message:", data[1])
        myEmit('message update', {'message': data[1], 'timestamp': getTimestamp() })
    else:
        print("Unknown buffer item", data)
    bufferUpdate()
    
def bufferUpdate():
    myEmit('buffer update', { 'bufferList': [str(hash(a)) for a in buffer],
                            'bufferData': {}, 
                            'bufferRunning': alive,
                            'bufferPaused': paused,
                            'bufferPausePen': getPenData() })

def serialCommunicator(sender):
    with app.test_request_context("/"):
        while True:
            bufferData.wait()
            if not alive:
                break
            while not paused and buffer:
                sendBufferLine()
            bufferData.clear()

if __name__ == '__main__':
    if len(sys.argv) >= 2:
        port = sys.argv[1]
    else:
        port = "auto"
    if len(sys.argv) >= 3:
        speed = int(sys.argv[2])
    else:
        speed = 115200
    communicator = threading.Thread(target=serialCommunicator,args=(GCodeSender(port,speed),))
    communicator.daemon = True
    communicator.start()
    app.run(debug=True,use_reloader=False,port=42420)
