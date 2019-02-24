#!flask/bin/python
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whocares'
socketio = SocketIO(app)

penHeight = 0.75 # 0=up, 1=down
penX = 0
penY = 0
servoHeight = 0
tool = "red"
lastDuration = 0
distanceCounter = 0
bufferCount = 0
paused = False

def getPenData():
    return { 'x': penX, 'y': penY, 'state':1, 'height': servoHeight, 
             'power': 0, 'tool': tool, 'lastDuration': lastDuration,
             distanceCounter: distanceCounter, 'simulation': 0 }

@socketio.on('connect')
def chat_connect():
    print ('socket.io connected')
    
    emit('pen update', getPenData())

@socketio.on('disconnect')
def chat_disconnect():
    print ("Client disconnected")

@socketio.on('broadcast')
def chat_broadcast(message):
    print ("test")
    emit("chat", {'data': message['data']})
    
@socketio.on('message')
def handle_message(message):
    print('received message: ' + message)

def addCallback(cb):
    print('TODO callback: ' + cb)
    
def clearBuffer():
    print("TODO: clearBuffer")
    return jsonify( { 'status': 'buffer cleared' } )

@app.route('/')
def index():
    return "Hello, World!"

@app.route('/v1/pen', methods=['GET','PUT'])
def handle_pen(task_id=None):
    if request.method == 'GET':
        return jsonify(getPenData())
    else:
        print('pen request:', request.json)
        return jsonify(getPenData())
    

@app.route('/v1/buffer', methods=['GET','POST','PUT','DELETE'])
def handle_buffer(task_id=None):
    def getData():
        return jsonify({'running': False, 'paused': paused, 'count': bufferCount, 'buffer': ['hello']})
    if request.method == 'DELETE':
        return clearBuffer()
    elif request.method == 'GET':
        return getData()
    elif request.method == 'PUT':
        paused = request.json.get('paused', False)
        print('paused',paused)
        return getData()
    elif request.method == 'POST':
        msg = request.json.get('message',None)
        if msg:
            print(msg)
        cb = request.json.get('callback',None)
        if cb:
            addCallback(cb)
        return jsonify({'status': "Message added to buffer"})

#@app.route('/socket.io/', methods=['GET'])
#def handle_socket_io(task_id=None):
#    print('socket')
#    return handle_pen()
        
def get_tasks():
    pass

if __name__ == '__main__':
    app.run(debug=True,port=42420)
    