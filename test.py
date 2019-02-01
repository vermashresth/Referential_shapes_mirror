import pickle
import numpy as np
import random
from datetime import datetime
import os

import torch
from model import Sender, Receiver, Model, BaselineNN
from run import train_one_epoch, evaluate
from utils import get_lr_scheduler
from dataloader import load_data

use_gpu = torch.cuda.is_available()

prev_model_file_name = None#'dumps/01_26_00_16/01_26_00_16_915_model'

EPOCHS = 1000 if use_gpu else 2
EMBEDDING_DIM = 256
HIDDEN_SIZE = 512
BATCH_SIZE = 128 if use_gpu else 4
MAX_SENTENCE_LENGTH = 13 if use_gpu else 5
START_TOKEN = '<S>'
K = 3  # number of distractors

# Load data
(word_to_idx, idx_to_word, bound_idx, vocab_size, n_image_features, 
	train_data, valid_data, test_data) = load_data(BATCH_SIZE, K)

# Settings
dumps_dir = './dumps'
if not os.path.exists(dumps_dir):
	os.mkdir(dumps_dir)

if prev_model_file_name == None:
	model_id = '{:%m_%d_%H_%M}'.format(datetime.now())
	starting_epoch = 0
else:
	last_backslash = prev_model_file_name.rfind('/')
	last_underscore = prev_model_file_name.rfind('_')
	second_last_underscore = prev_model_file_name[:last_underscore].rfind('_')
	model_id = prev_model_file_name[last_backslash+1:second_last_underscore]
	starting_epoch = int(prev_model_file_name[second_last_underscore+1:last_underscore])

current_model_dir = '{}/{}'.format(dumps_dir, model_id)

if not os.path.exists(current_model_dir):
	os.mkdir(current_model_dir)


model = Model(n_image_features, vocab_size,
	EMBEDDING_DIM, HIDDEN_SIZE, BATCH_SIZE, use_gpu)

baseline = BaselineNN(n_image_features * (K+1), HIDDEN_SIZE, use_gpu)


if prev_model_file_name is not None:
	state = torch.load(prev_model_file_name, map_location= lambda storage, location: storage)
	model.load_state_dict(state)

	baseline_state = torch.load(prev_model_file_name.replace('model', 'baseline'), map_location= lambda storage, location: storage)
	baseline.load_state_dict(baseline_state)


if use_gpu:
	model = model.cuda()
	baseline = baseline.cuda()

optimizer = torch.optim.Adam(model.parameters(), lr=0.0001)
baseline_optimizer = torch.optim.Adam(baseline.parameters(), lr=0.001)
# lr_scheduler = get_lr_scheduler(optimizer)

# Train
if prev_model_file_name == None:
	losses_meters = []
	eval_losses_meters = []

	accuracy_meters = []
	eval_accuracy_meters = []
else:
	losses_meters = pickle.load(open('{}/{}_{}_losses_meters.p'.format(current_model_dir, model_id, starting_epoch), 'rb'))
	eval_losses_meters = pickle.load(open('{}/{}_{}_eval_losses_meters.p'.format(current_model_dir, model_id, starting_epoch), 'rb'))

	accuracy_meters = pickle.load(open('{}/{}_{}_accuracy_meters.p'.format(current_model_dir, model_id, starting_epoch), 'rb'))
	eval_accuracy_meters = pickle.load(open('{}/{}_{}_eval_accuracy_meters.p'.format(current_model_dir, model_id, starting_epoch), 'rb'))


for epoch in range(EPOCHS):
	e = epoch + starting_epoch

	epoch_loss_meter, epoch_acc_meter, messages = train_one_epoch(
		model, train_data, optimizer, word_to_idx, START_TOKEN, MAX_SENTENCE_LENGTH,
		baseline, baseline_optimizer)

	losses_meters.append(epoch_loss_meter)
	accuracy_meters.append(epoch_acc_meter)

	eval_loss_meter, eval_acc_meter, eval_messages = evaluate(
		model, valid_data, word_to_idx, START_TOKEN, MAX_SENTENCE_LENGTH,
		baseline)

	eval_losses_meters.append(eval_loss_meter)
	eval_accuracy_meters.append(eval_acc_meter)

	print('Epoch {}, average train loss: {}, average val loss: {}, average accuracy: {}, average val accuracy: {}'.format(
		e, losses_meters[e].avg, eval_losses_meters[e].avg, accuracy_meters[e].avg, eval_accuracy_meters[e].avg))

	# lr_scheduler.step(eval_acc_meter.avg)

	# Dump models
	torch.save(model.state_dict(), '{}/{}_{}_model'.format(current_model_dir, model_id, e))
	torch.save(baseline.state_dict(), '{}/{}_{}_baseline'.format(current_model_dir, model_id, e))

	# Dump stats
	pickle.dump(losses_meters, open('{}/{}_{}_losses_meters.p'.format(current_model_dir, model_id, e), 'wb'))
	pickle.dump(eval_losses_meters, open('{}/{}_{}_eval_losses_meters.p'.format(current_model_dir, model_id, e), 'wb'))
	pickle.dump(accuracy_meters, open('{}/{}_{}_accuracy_meters.p'.format(current_model_dir, model_id, e), 'wb'))
	pickle.dump(eval_accuracy_meters, open('{}/{}_{}_eval_accuracy_meters.p'.format(current_model_dir, model_id, e), 'wb'))

	# Dump messages
	pickle.dump(messages, open('{}/{}_{}_messages.p'.format(current_model_dir, model_id, e), 'wb'))
	pickle.dump(eval_messages, open('{}/{}_{}_eval_messages.p'.format(current_model_dir, model_id, e), 'wb'))


# Evaluate best model on test data

best_epoch = np.argmax([m.avg for m in eval_accuracy_meters])
best_model = Model(n_image_features, vocab_size,
	EMBEDDING_DIM, HIDDEN_SIZE, BATCH_SIZE, use_gpu)
best_model_name = '{}/{}_{}_model'.format(current_model_dir, model_id, best_epoch)
state = torch.load(best_model_name, map_location= lambda storage, location: storage)
best_model.load_state_dict(state)

baseline = BaselineNN(n_image_features * (K+1), HIDDEN_SIZE, use_gpu)
baseline_state = torch.load(best_model_name.replace('model', 'baseline'), map_location= lambda storage, location: storage)
baseline.load_state_dict(baseline_state)

if use_gpu:
	best_model = best_model.cuda()
	baseline = baseline.cuda()


_, test_acc_meter, _ = evaluate(best_model, test_data, word_to_idx, START_TOKEN, MAX_SENTENCE_LENGTH, baseline)

print('Test accuracy: {}'.format(test_acc_meter.avg))

pickle.dump(test_acc_meter, open('{}/{}_{}_test_accuracy_meter.p'.format(current_model_dir, model_id, best_epoch), 'wb'))