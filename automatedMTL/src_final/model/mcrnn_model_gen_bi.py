import tensorflow as tf
import numpy as np
import os
import cPickle as pickle
from os.path import expanduser
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","util")))
from tf_utils import fcLayer, createLSTMCell, applyActivation, predictionLayer, compute_cost
#from predContext import predContext, createHtDict

class model(object):

        # Task params
        is_multi_task = True
        secondary_task = "word generation"
        primary_task = "classification"

        # Model params
        # 0 -- shared;  1 -- context;  2 -- task
        is_bidirectional = True
	fc_activation = "tanh"
	context_output_activation = "tanh"
	task_output_activation = "softmax"
	dropout = 0.0
	body_lstm_size = 128
	context_lstm_size = 128
	task_lstm_size = 128
	body_n_layer = 1
	context_n_layer = 1
	task_n_layer = 1
	context_branch_fc = 512
	task_branch_fc = 512
        context_fc_input_size = context_lstm_size
        task_fc_input_size = task_lstm_size
	if is_bidirectional:
            context_fc_input_size = 2*context_lstm_size
            task_fc_input_size = 2*task_lstm_size

	# Data params
	n_classes = 2
	batch_size = 128
	max_length = 52
	feature_length = 300
 	context_dim = 300
	task_dim = n_classes

	# Hyper- params
	lr = 0.0001 #hp
        lr_mod = 0.5 #hp
	context_lr = lr_mod*lr
	n_epoch = 100 #hp
	keep_prob_val = 1.0


        def rnn_layer(self, fw_cell, bw_cell, rnn_inputs, is_bidirectional):
            if is_bidirectional:
                outputs, last_states = tf.nn.bidirectional_dynamic_rnn(cell_fw=fw_cell, cell_bw=bw_cell, inputs=rnn_inputs, sequence_length=self.length(rnn_inputs), dtype=tf.float32)
	    else:
		outputs, last_states = tf.nn.dynamic_rnn(cell=fw_cell, dtype=tf.float32, sequence_length=self.length(rnn_inputs), inputs=rnn_inputs)
	    return outputs, last_states


	def buildModel(self, x, y_context, y_task, is_train, dropout, scope="multiTask"):
    	    
	    context_cost = tf.constant(0)
    	    task_cost = tf.constant(0.0, dtype=tf.float32)

    	    # Assume the input shape is (batch_size, max_length, feature_length)
    	    # TASK = primary task, CONTEXT = secondary task

	    # Create the forward cell for all LSTMs
            body_lstm_cell, _ = createLSTMCell(self.batch_size, self.body_lstm_size, self.body_n_layer, forget_bias=0.0)
            context_lstm_cell, _ = createLSTMCell(self.batch_size, self.context_lstm_size, self.context_n_layer, forget_bias=0.0)
	    task_lstm_cell, _ = createLSTMCell(self.batch_size, self.task_lstm_size, self.task_n_layer, forget_bias=0.0)

	    if self.is_bidirectional:
	        # Create the backward cell for LSTM  
                body_lstm_cell_bw, _ = createLSTMCell(self.batch_size, self.body_lstm_size, self.body_n_layer, forget_bias=0.0)
                context_lstm_cell_bw, _ = createLSTMCell(self.batch_size, self.context_lstm_size, self.context_n_layer, forget_bias=0.0)
	        task_lstm_cell_bw, _ = createLSTMCell(self.batch_size, self.task_lstm_size, self.task_n_layer, forget_bias=0.0)
           

            if not self.is_multi_task: context_output = tf.constant(0)

    	    with tf.variable_scope("shared_lstm"):
        	body_cell_output, last_body_state = self.rnn_layer(fw_cell=body_lstm_cell, bw_cell=body_lstm_cell_bw, rnn_inputs=x, is_bidirectional=self.is_bidirectional)

            if self.is_multi_task:
    	        with tf.variable_scope("context_branch"):
		    # The output from bidirectional LSTM is a list = [fw_output, bw_output], each of size (batch_size, max_length, out_size)
		    if self.is_bidirectional:
			# Concatenate the input of both directions along the feature dimension axis 2(300 -> 600)
		        context_input = tf.concat(body_cell_output, axis=2)
		        context_cell_output, last_context_state = self.rnn_layer(fw_cell=context_lstm_cell, bw_cell=context_lstm_cell_bw, rnn_inputs=context_input, is_bidirectional=self.is_bidirectional)
	            else:
			context_input = body_cell_output
		        context_cell_output, last_context_state = self.rnn_layer(fw_cell=context_lstm_cell, bw_cell=None, rnn_inputs=context_input, is_bidirectional=self.is_bidirectional)

    	            # The output from LSTMs will be (batch_size, max_length, out_size)

        	    # Select the last output that is not generated by zero vectors
                    if self.secondary_task == "missing word":
			if self.is_bidirectional:
			    last_context_output_fw = self.last_relevant(context_cell_output[0], self.length(context_cell_output[0]))
			    last_context_output_bw = self.last_relevant(context_cell_output[1], self.length(context_cell_output[1]))
			    last_context_output = tf.concat([last_context_output_fw, last_context_output_bw], axis=2)
                        else:
        	            last_context_output = self.last_relevant(context_cell_output, self.length(context_cell_output))
        	        # feed the last output to the fc layer and make prediction
    	                with tf.variable_scope("context_fc"):
        	            context_fc_out = fcLayer(x=last_context_output, in_shape=self.contxt_fc_input_size, out_shape=self.context_branch_fc, activation=self.fc_activation, dropout=self.dropout, is_train=is_train, scope="fc1")
        	        with tf.variable_scope("context_pred"):
		            context_output, context_logits = predictionLayer(x=context_fc_out, y=y_context, in_shape=self.context_branch_fc, out_shape=y_context.get_shape()[-1].value, activation=self.context_output_activation)
		            context_cost = compute_cost(logit=context_logits, y=y_context, out_type="last_only", max_length=self.max_length, batch_size=self.batch_size, embed_dim=self.feature_length, activation=self.context_output_activation)

                    if self.secondary_task == "word generation":
			if self.is_bidirectional:
			    context_cell_output = tf.concat([context_cell_output[0], context_cell_output[1]], axis=2) #(batch_size, max_length, 2*out_size)
			    context_cell_output = tf.transpose(context_cell_output, [1, 0, 2]) #(max_length, batch_size, 2*out_size)
			    context_cell_output = tf.reshape(context_cell_output, [-1, 2*self.context_lstm_size])

			    #context_cell_output_fw = tf.transpose(context_cell_output[0], [1, 0, 2])
 	                    #context_cell_output_fw = tf.reshape(context_cell_output_fw, [-1, self.context_lstm_size])
			    #context_cell_output_bw = tf.transpose(context_cell_output[1], [1, 0, 2])
 	                    #context_cell_output_bw = tf.reshape(context_cell_output_bw, [-1, self.context_lstm_size])
			    #context_cell_output = tf.concat([context_cell_output_fw, context_cell_output_bw], axis=2) #The flattened and concatenated vector is (batch, 2*lstm_size)
			    
			else:
			    context_cell_output = tf.transpose(context_cell_output, [1, 0, 2])
 	                    context_cell_output = tf.reshape(context_cell_output, [-1, self.context_lstm_size])
                        context_output_list = tf.split(context_cell_output, self.max_length, 0)

                        fc_output_list = []
			with tf.variable_scope("context_fc"):
		            for step in range(self.max_length):
			        if step > 0: tf.get_variable_scope().reuse_variables()
			        fc_out = fcLayer(x=context_output_list[step], in_shape=self.context_fc_input_size, out_shape=self.context_branch_fc, activation=self.fc_activation, dropout=self.dropout, is_train=is_train, scope="fc1")
			        fc_output_list.append(tf.expand_dims(fc_out, axis=1))
                            print len(fc_output_list)
			    print fc_output_list[0].get_shape()
			    context_fc_out = tf.concat(fc_output_list, axis=1)
                            print "context fc output shape before transpose: ", context_fc_out.get_shape()
			
			with tf.variable_scope("context_pred"):
        	            context_output, context_logits = predictionLayer(x=context_fc_out, y=y_context, in_shape=self.context_branch_fc, out_shape=y_context.get_shape()[-1].value, activation=self.context_output_activation)
		            print "Context prediction output shape: ", context_output.get_shape()
			    context_cost = compute_cost(logit=context_logits, y=y_context, out_type="sequential", max_length=self.max_length, batch_size=self.batch_size, embed_dim=self.feature_length,activation=self.context_output_activation)


		    print "Context cost shape: ", context_cost.get_shape()

    	    with tf.variable_scope("task_branch"):
		if self.is_bidirectional:
		    task_input = tf.concat(body_cell_output, axis=2)
		    task_cell_output, last_task_state = self.rnn_layer(fw_cell=task_lstm_cell, bw_cell=task_lstm_cell_bw, rnn_inputs=task_input, is_bidirectional=self.is_bidirectional)
		else:
		    task_input = body_cell_output
                    task_cell_output, last_task_state = self.rnn_layer(fw_cell=task_lstm_cell, bw_cell=None, rnn_inputs=task_input, is_bidirectional=self.is_bidirectional)

    	    	with tf.variable_scope("task_fc"):
        	    # Select the last output that is not generated by zero vectors
		    if self.is_bidirectional:
			last_task_output_fw = self.last_relevant(task_cell_output[0], self.length(task_cell_output[0]))
			last_task_output_fw = tf.expand_dims(last_task_output_fw, axis=0)
			last_task_output_bw = self.last_relevant(task_cell_output[1], self.length(task_cell_output[1]))
			last_task_output_bw = tf.expand_dims(last_task_output_bw, axis=0)
			last_task_output = tf.concat([last_task_output_fw, last_task_output_bw], axis=2)
			last_task_output = tf.squeeze(last_task_output)
		    else:    
        	        last_task_output = self.last_relevant(task_cell_output, self.length(task_cell_output))
        	    # feed the last output to the fc layer and make prediction
        	    task_fc_out = fcLayer(x=last_task_output, in_shape=self.task_fc_input_size, out_shape=self.task_branch_fc, activation=self.fc_activation, dropout=self.dropout, is_train=is_train, scope="fc2")
        	    task_output, task_logits = predictionLayer(x=task_fc_out, y=y_task, in_shape=self.context_branch_fc, out_shape=y_task.get_shape()[-1].value, activation=self.task_output_activation)
		    task_cost = compute_cost(logit=task_logits, y=y_task, out_type="last_only", max_length=self.max_length, batch_size=self.batch_size, embed_dim=self.feature_length, activation=self.task_output_activation)

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





