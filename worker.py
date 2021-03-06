#the point now is to create a worker that can use instructions.
import boto3
import json
from subprocess import call
from subprocess import check_output
from helper import *
from threading import Thread
import time
import decimal
import mpu

class Worker():

	def __init__(self):
		
		"""
		Connect to AWS s3 download full swarms parameters. Set the file this 
		will be reading from and the file this will be writing too. 
		"""
		self.direc = get_parent()
		self.params = {}
		self.s3 = boto3.resource('s3')
		self.my_id = check_output(['curl', 'http://169.254.169.254/latest/meta-data/instance-id'])
		self.my_id = "".join(map(chr, self.my_id))
		self.sqs = boto3.resource('sqs', region_name='us-east-1')
		self.state = ['waiting']
		self.queue = self.sqs.get_queue_by_name(QueueName='swarm.fifo')
		self.controller_listener = Thread(target=self.check_in, daemon=True)
		self.controller_listener.start()
		# self.s3.Bucket('swarm-instructions').download_file('instructions.txt', self.file_in)
		self.dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
		self.table = self.dynamodb.Table('test')
		"""JSON SPECIFIC VARIABLES"""
		self.file_out = None
		self.data = None
		self.s3.Bucket('swarm-instructions').download_file('parameters.txt', 'parameters.txt')

	def check_in(self):
		while True:
			with open(self.direc + '/state.txt', 'r') as f:
				self.state[0] = f.read()
				time.sleep(3)

	def extract(self):
		"""
		Use the file_in from init to extract this workers specific parameters
		from json dictionary based on ec2 instance ids
		"""		
		with open('parameters.txt', 'r') as f:
			swarm_params = json.load(f)
		self.params = swarm_params[self.my_id]
		self.s3.Bucket('swarm-instructions').download_file('data/' + self.params['json'], 'data.json')
		self.params['json'] = mpu.io.read('data.json')


	def run(self):
		"""
		Take the params from extract and run whatever operations you want
		on them. Set self.results in this method based on self.params
		"""
		work_load = self.params['work_load']
		scaler = self.params['random_num']
		json = self.params['json']
		size = len(json)
		i = 0
		while self.state[0] == 'waiting':
			print("Waiting for GO") 
			time.sleep(.3)

		i = 0
		start = time.clock()
		while i < int(work_load * scaler) and self.state[0] != 'exit':
			if i%100 == 0:
				self.report(i, size=int(work_load * scaler))
			while self.state[0] == 'pause':
				time.sleep(.3)
				self.report(i,size=size)
			i += 1
		end = time.clock()
		self.put_in_Dynamo(self.my_id,(end-start), work_load, scaler)

	def put_in_Dynamo(self, *args):
		_id,time, work_load, scaler = args
		response = self.table.update_item(
		    Key={
		    'id': self.my_id
		    },
		    UpdateExpression='SET #y = :val2, #z = :val3, #p = :val4',
		    ExpressionAttributeNames={
		        '#y': 'time',
		        '#z': 'work_load',
		        '#p': 'scaler'

		    },
		    ExpressionAttributeValues={
		        ':val2': decimal.Decimal(str(time)),
		        ':val3': decimal.Decimal(work_load),
		        ':val4': decimal.Decimal(str(scaler))
		    }
		)

	def create_image(self,elem):
		#print(elem)
		print(elem['imageId'])
		try:
			response = requests.get(elem['url'],timeout=2)
		except:
			return "Failed"
		return np.array(Image.open(BytesIO(response.content)).convert('RGB').resize((64,64)))

		


	def report(self,i, size = 100):
		"""
		Post to swarm queue my progress and state
		"""
		d = {
		'message': 'working',
		'state': self.state[0],
		'id': self.my_id,
		'progress': round(i/size,4)}
		response = self.queue.send_message(MessageBody=json.dumps(d), MessageGroupId='bots')

	def dump(self):
		"""
		Use the file_out to write the results of this worker to s3.
		"""
		d = {
		'message': 'complete',
		'state': self.state[0],
		'id': self.my_id,
		'progress': 'None'}
		response = self.queue.send_message(MessageBody=json.dumps(d), MessageGroupId='bots')


		



