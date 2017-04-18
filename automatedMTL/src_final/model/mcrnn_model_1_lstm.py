import tensorflow as tf
import numpy as np
import os
import cPickle as pickle
from os.path import expanduser
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","util")))
from tf_utils import fcLayer, createLSTMCell, createGRUCell, applyActivation, predictionLayer, compute_cost
#from predContext import predContext, createHtDict

class model(object):

        # Task params
        is_multi_task = True
        secondary_task = "word generation"
        primary_task = "classification"

        # Model params
        # 0 -- shared;  1 -- context;  2 -- task
	fc_activation = "tanh"
	context_output_activation = "tanh"
	task_output_activation = "softmax"
	body_lstm_size = 1024
	body_n_layer = 1
	context_n_layer = 1
	task_n_layer = 1
	context_branch_fc = 512
	task_branch_fc = 30

	# Data params
	n_classes = 2
	batch_size = 64
	max_length = 52
	feature_length = 300
 	context_dim = 300
	task_dim = n_classes

	# Hyper- params
	lr = 0.0001 #hp
        lr_mod = 1.0 #hp
	context_lr = lr_mod*lr
	n_epoch = 50 #hp

	def buildModel(self, x, y_context, y_task, is_train, dropout, scope="multiTask"):

    	    # Assume the input shape is (batch_size, max_length, feature_length)

    	    #TASK = primary task, CONTEXT = secondary task

    	    # Create lstm cell for the shared layer
            body_lstm_cell, _ = createLSTMCell(self.batch_size, self.body_lstm_size, self.body_n_layer, forget_bias=0.0)

    	    context_cost = tf.constant(0)
    	    task_cost = tf.constant(0.0, dtype=tf.float32)

            if not self.is_multi_task: context_output = tf.constant(0)

    	    with tf.variable_scope("shared_lstm"):
        	body_cell_output, last_body_state = tf.nn.dynamic_rnn(cell = body_lstm_cell, dtype=tf.float32, sequence_length=self.length(x), inputs=x)

            if self.is_multi_task:
    	        with tf.variable_scope("context_branch"):
        	    # Select the last output that is not generated by zero vectors
                    if self.secondary_task == "missing word":
        	        last_body_output = self.last_relevant(body_cell_output, self.length(body_cell_output))
        	        # feed the last output to the fc layer and make prediction
    	                with tf.variable_scope("context_fc"):
        	            context_fc_out = fcLayer(x=last_body_output, in_shape=self.body_lstm_size, out_shape=self.context_branch_fc, activation=self.fc_activation, dropout=dropout, is_train=is_train, scope="fc1")
        	        with tf.variable_scope("context_pred"):
		            context_output, context_logits = predictionLayer(x=context_fc_out, y=y_context, in_shape=self.context_branch_fc, out_shape=y_context.get_shape()[-1].value, activation=self.context_output_activation)
		            context_cost = compute_cost(logit=context_logits, y=y_context, out_type="last_only", max_length=self.max_length, batch_size=self.batch_size, embed_dim=self.feature_length, activation=self.context_output_activation)

                    if self.secondary_task == "word generation":
			context_input = tf.transpose(body_cell_output, [1, 0, 2])
 	                context_input = tf.reshape(context_input, [-1, self.body_lstm_size])
                        context_input_list = tf.split(context_input, self.max_length, 0)
                        fc_output_list = []
			with tf.variable_scope("context_fc"):
		            for step in range(self.max_length):
			        if step > 0: tf.get_variable_scope().reuse_variables()
			        fc_out = fcLayer(x=context_input_list[step], in_shape=self.body_lstm_size, out_shape=self.context_branch_fc, activation=self.fc_activation, dropout=dropout, is_train=is_train, scope="fc1")
			        fc_output_list.append(tf.expand_dims(fc_out, axis=1))
			    context_fc_out = tf.concat(fc_output_list, axis=1)
			with tf.variable_scope("context_pred"):
        	            context_output, context_logits = predictionLayer(x=context_fc_out, y=y_context, in_shape=self.context_branch_fc, out_shape=y_context.get_shape()[-1].value, activation=self.context_output_activation)
			    context_cost = compute_cost(logit=context_logits, y=y_context, out_type="sequential", max_length=self.max_length, batch_size=self.batch_size, embed_dim=self.feature_length,activation=self.context_output_activation)


		    print "Context cost shape: ", context_cost.get_shape()

    	    with tf.variable_scope("task_branch"):
    	    	with tf.variable_scope("task_fc"):
        	    # Select the last output that is not generated by zero vectors
        	    last_body_output = self.last_relevant(body_cell_output, self.length(body_cell_output))
        	    # feed the last output to the fc layer and make prediction
        	    task_fc_out = fcLayer(x=last_body_output, in_shape=self.body_lstm_size, out_shape=self.task_branch_fc, activation=self.fc_activation, dropout=dropout, is_train=is_train, scope="fc2")
        	    task_output, task_logits = predictionLayer(x=task_fc_out, y=y_task, in_shape=self.task_branch_fc, out_shape=y_task.get_shape()[-1].value, activation=self.task_output_activation)
		    print "Task output shape: ", task_output.get_shape()
		    task_cost = compute_cost(logit=task_logits, y=y_task, out_type="last_only", max_length=self.max_length, batch_size=self.batch_size, embed_dim=self.n_classes,activation=self.task_output_activation)

            return context_cost, task_cost, task_output, context_output

	# Flatten the output tensor to shape features in all examples x output size
	# construct an index into that by creating a tensor with the start indices for each example tf.range(0, batch_size) x max_length
	# and add the individual sequence lengths to it
	# tf.gather() then performs the acutal indexing.
	def last_relevant(self, output, length):
    	    index = tf.range(0, self.batch_size) * self.max_length + (length - 1)
            out_size = int(output.get_shape()[2])
    	    flat = tf.reshape(output, [-1, out_size])
   	    relevant = tf.gather(flat, index)
    	    return relevant

# Assume that the sequences are padded with 0 vectors to have shape (batch_size, max_length, feature_length)

        def length(self, sequence):
            used = tf.sign(tf.reduce_max(tf.abs(sequence), reduction_indices=2))
            length = tf.reduce_sum(used, reduction_indices=1)
            length = tf.cast(length, tf.int32)
            print length.get_shape()
            return length





