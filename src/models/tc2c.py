'''
Keras backend. LSTM Model.

Using standard default range:
Input: (65x1) 64 unique chars, 1 EOS char
Output: (65x1) 64 unique chars, 1 EOS char

'''
import cPickle as pickle
import  numpy as np
import h5py
import os
import sys
from os.path import expanduser
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","utils")))
from loadDataNewModel import loadData
from predContext import predContext, createHtDict
from keras.utils import np_utils
from keras.models import Sequential
from keras.layers import LSTM
from keras.layers import Dense
from keras.layers import PReLU
from keras.layers import Activation
from keras.layers.wrappers import TimeDistributed
from keras.optimizers import RMSprop
from keras.optimizers import Adagrad
from keras.layers import Dropout
from keras.layers import BatchNormalization
from tweetGenerator_lstm import generateText
from keras.callbacks import ModelCheckpoint
from logger import logger
import time

#sequenceLength: sequence length (k in BPTTk)
sequenceLength = 30
#Number of symbols
vocabLen = 66
#train test split
trainPercent = 0.9
#threshold on hashtag frequency 
freqThreshold = 84

logAllPredictions=True
#X: [# Seuqences, 40 (sequenceLength), 65(inputSize)].
#y: [# Sequences, 300]

print("Start loading data ...")
trainTweets, trainHashtags, testTweets, testHashtags, trainX, trainY, testX, testY, trainTweetSequence, trainHashtagSequence, testTweetSequence, testHashtagSequence, trainContextSequence, testContextSequence, dictionary, nUniqueHt = loadData({},np.array([]), sequenceLength, trainPercent, freqThreshold)
print("Finished loading data")


#initialize some hyper-parameters
topN = np.ceil(0.05*nUniqueHt).astype(int)
print  topN


#embeddingLength: size of the word embedding
embeddingLength = 300

#inputSize: size of each input vector (default: 365x1)
inputSize = vocabLen + embeddingLength

#numHiddenFirst: size of first hidden layer
numHiddenFirst = 512

#Number of testing/training tweets
nTestData = len(testTweets)
nTrainData = len(trainTweets)
nTestSequences = len(testTweetSequence)
nTrainSequences = len(trainTweetSequence)
print "Number of testing sequences: ", nTestSequences
print "Number of training sequences: ", nTrainSequences
print "Number of testing tweets: ", nTestData
print "Number of training tweets: ", nTrainData

dictionary = pickle.load(open(expanduser("~/tweetnet/data/word2vec_dict.pkl")))

# Create the hashtag dictionary
htDic = createHtDict(dictionary, testHashtags)

numEpochs=50

#building cLSTM model
#print("\n")
print("Start building model ....")
model = Sequential()

#model.add(TimeDistributed(Dense(numHiddenFirst), input_shape=(sequenceLength, inputSize)))
#model.add(BatchNormalization())

model.add(LSTM(numHiddenFirst, input_shape=(sequenceLength, inputSize)))
model.add(BatchNormalization())

model.add(Dense(numHiddenFirst))
model.add(PReLU())
model.add(BatchNormalization())

model.add(Dense(embeddingLength))
model.add(PReLU())

optimizer = RMSprop(lr=0.005)

model.compile(loss='mean_squared_error', optimizer=optimizer)
print("Finished building model.")

model.summary()

name = "t2c"+time.strftime("%Y-%m-%d_%H:%M") + ".log"
for epoch in range(numEpochs):
    
    model.fit(trainX, trainY, nb_epoch=1, batch_size=128)
     
    correctCnt = 0
    randIdx = np.random.randint(0, nTestData, 10)
 
    tweetCnt = 0
    tweetStartIdx = 0
    log = []
    log.append([epoch])
    for testIdx in range(nTestSequences):
        # Stack the windows (1 x 40 x 65) of each tweet as a 3D matrix (#windows x 40 x 65)
        if testTweetSequence[testIdx][-1] == chr(3):
            oneTweet = testX[tweetStartIdx:testIdx+1, :, :]
            modelOutput = model.predict(oneTweet)
            topNht, isCorrect, topNdist = predContext(htDic, modelOutput, topN, testHashtags[tweetCnt])
            tweetStartIdx = testIdx + 1
            if isCorrect:
                correctCnt += 1
                isCorrect = True
            if tweetCnt in randIdx:
                print testTweets[tweetCnt][:-2]
                print "Given label is ", testContextSequence[testIdx]
                print "True label is ", testHashtags[tweetCnt]
                print "Top ", topN, " hashtags are ", topNht
            
            if logAllPredictions:
                log.append([testTweets[tweetCnt][:-2],testHashtags[tweetCnt],isCorrect,topNht])
            tweetCnt += 1
    accuracy = correctCnt*1.0 / nTestData
    log.append([correctCnt, accuracy])        
    logger(log,name)




