'''
loads twitter dataset from storm API.
'''
import sys
import os
import numpy as np
import cPickle as pickle
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","utils")))
from ReducedAsciiDictionary import ReducedAsciiDictionary
from getEnglishHashTweets import checkHashtags
from numpy import random
from random import shuffle
from os.path import expanduser

def normByThreshold(tweets, hashtags, missingWords, freqThreshold):

    #load hashtag frequency dictionary
    hashtagFreq = pickle.load(open(expanduser("~/tweetnet/data/hashtagFreq.pkl"), "rb"))
    tweets_shuf = []
    hashtags_shuf = []
    missingWords_shuf = []
    idx_shuf = range(len(tweets))
    shuffle(idx_shuf)
    hashtagFreqCnt = {}
    for i in idx_shuf:

        ht = hashtags[i]
        mw = missingWords[i]

        if hashtagFreq[ht] >= freqThreshold:
            if hashtagFreqCnt.get(ht) == None:

                hashtagFreqCnt[ht] = 1
                tweets_shuf.append(tweets[i])
                hashtags_shuf.append(ht)
                missingWords_shuf.append(mw)

            elif hashtagFreqCnt[ht] < freqThreshold:

                hashtagFreqCnt[ht] += 1
                tweets_shuf.append(tweets[i])
                hashtags_shuf.append(ht)
                missingWords_shuf.append(mw)
    print len(hashtagFreqCnt)
    print hashtagFreqCnt

    return tweets_shuf, hashtags_shuf, missingWords_shuf


def loadData(dictionary,ranges,sequenceLength,trainPercent, freqThreshold):
	''' Creates dataset based on dictionary, a set of ascii
	ranges, and pickled twitter data from Apache Storm.


        X: [#sequences, 40, 65]
        y: [#sequences, 300]
	vocabLen: (dictionary length)
	tweetLength: (numTweets)
	'''

        #load tweets with >=2 hashtags and corresponding english hashtags
        tweets = pickle.load(open(expanduser("~/tweetnet/data/multitaskTweets.pkl"), "rb"))  # a list of tweet strings
        hashtags = pickle.load(open(expanduser("~/tweetnet/data/multitaskHashtags.pkl"), "rb")) # a list of hashtags
        missingWords = pickle.load(open(expanduser("~/tweetnet/data/multitaskTweetMw.pkl"), "rb")) # a list of words
 
	tweets_shuf, hashtags_shuf, missingWords_shuf = normByThreshold(tweets, hashtags, missingWords, freqThreshold)

	nTweet = len(tweets_shuf)
        nTrainData = np.ceil(nTweet*trainPercent).astype(int)
        
        #Split the tweets and hashtags into training and testing set 
        trainTweets = tweets_shuf[0: nTrainData]
        trainHashtags = hashtags_shuf[0: nTrainData]
        trainMw = missingWords_shuf[0: nTrainData]

        testTweets = tweets_shuf[nTrainData: nTweet]
        testHashtags = hashtags_shuf[nTrainData: nTweet]
        testMw = missingWords_shuf[nTrainData: nTweet]

        nTestData = len(testTweets)

        
        #load word2vec dictionary
        print("Loading word2vec dictionary")
        word2vecDict = pickle.load(open(expanduser("~/tweetnet/data/word2vec_dict.pkl"), "rb"))
        print("Finished loading word2vec dictionary")
        
	#create character dictionary for tweets.
	dictionary = ReducedAsciiDictionary({},ranges).dictionary
        dictionary[chr(2)] = len(dictionary)
        dictionary[chr(3)] = len(dictionary)
	#number of unique characters in dataset
	vocabLen = len(dictionary)

	#initialize datastore arrays
        trainTweetSequence = []
        trainHashtagSequence = []
        trainMwSequence = []

        testTweetSequence = []
        testHashtagSequence = []
        testMwSequence = []

	trainStartIdx = []
 	testStartIdx = []
	
        #vector in word2vec is 300
        embeddingLength = 300

        #Split data into sequences of length 40 for training
	sequenceCnt = 0
        for i in range(nTrainData):
            oneTweet = trainTweets[i]
            trainStartIdx.append(sequenceCnt)
            for j in range(0, len(oneTweet) - sequenceLength + 1, 1):
                trainTweetSequence.append(oneTweet[j : j+sequenceLength])
                trainHashtagSequence.append(trainHashtags[i])
                trainMwSequence.append(trainMw[i])
                sequenceCnt += 1
        print('Number of sequences in training data: ', len(trainTweetSequence))
        print('Number of hashtags in training data: ', len(trainHashtagSequence))
        print('Number of missing words in training data: ', len(trainMwSequence))


        sequenceCnt = 0
	#Split data into sequences of length 40 for testing
        for i in range(nTestData):
            oneTweet = testTweets[i]
            testStartIdx.append(sequenceCnt)
	    for j in range(0, len(oneTweet) - sequenceLength + 1, 1):
                testTweetSequence.append(oneTweet[j : j+sequenceLength])
                testHashtagSequence.append(testHashtags[i])
                testMwSequence.append(testMw[i])
                sequenceCnt += 1
        print('Number of sequences in testing data: ', len(testTweetSequence))
        print('Number of hashtags in testing data: ', len(testHashtagSequence))
	print('Number of missing words in testing data: ', len(testMwSequence))
	
        # for each sequence, create onehot encoding for each character
	print("Vectorization...")
        
        # trainX: [#training sequences, 40, 65]
        # trainy: [#training sequences, 300]
        trainX = np.zeros((len(trainTweetSequence), sequenceLength, vocabLen), dtype=np.bool)
        trainY_task = np.zeros((len(trainTweetSequence), embeddingLength))
        trainY_context = np.zeros((len(trainTweetSequence), embeddingLength))

	for i, seq in enumerate(trainTweetSequence):
            if i % 10000 == 0:
                print("Loading training tweet ", i)
	    for j, ch in enumerate(seq):
		oneHotIndex = dictionary.get(ch)
		trainX[i,j,oneHotIndex] = 1
                trainY_task[i] = word2vecDict[trainHashtagSequence[i]]	    
                trainY_context[i] = word2vecDict[trainMwSequence[i]]


        # testX: [#testing sequences, 40, 65]
        # testy: [#testing sequences, 300]
        testX = np.zeros((len(testTweetSequence), sequenceLength, vocabLen), dtype=np.bool)
        testY_task = np.zeros((len(testTweetSequence), embeddingLength))
        testY_context = np.zeros((len(testTweetSequence), embeddingLength))
        
	for i, seq in enumerate(testTweetSequence):
            if i % 10000 == 0:
                print("Loading testing tweet ", i)
	    for j, ch in enumerate(seq):
		oneHotIndex = dictionary.get(ch)
		testX[i,j,oneHotIndex] = 1
                testY_task[i] = word2vecDict[testHashtagSequence[i]]	  
                testY_context[i] = word2vecDict[testMwSequence[i]]

        train_data = [trainX, trainY_task, trainY_context]
        test_data = [testX, testY_task, testY_context]
        text_data = [testTweets, testHashtags, testMw, testTweetSequence, testHashtagSequence, testMwSequence, testStartIdx]

        with open(expanduser("~/tweetnet/data/train_data.pkl"), "wb") as file1:
            pickle.dump(train_data, file1, pickle.HIGHEST_PROTOCOL)
        with open(expanduser("~/tweetnet/data/test_data.pkl"), "wb") as file2:
            pickle.dump(test_data, file2, pickle.HIGHEST_PROTOCOL)
        with open(expanduser("~/tweetnet/data/text_data.pkl"), "wb") as file3:
            pickle.dump(text_data, file3, pickle.HIGHEST_PROTOCOL)

	return trainTweets, trainHashtags, trainMw, testTweets, testHashtags, testMw, trainX, trainY_task, trainY_context, testX, testY_task, testY_context,  trainTweetSequence, trainHashtagSequence, trainMwSequence, testTweetSequence, testHashtagSequence, testMwSequence, word2vecDict, trainStartIdx, testStartIdx


if __name__ == "__main__":
    trainTweets, trainHashtags, trainMw, testTweets, testHashtags, testMw, trainX, trainY_task, trainY_context, testX, testY_task, testY_context,  trainTweetSequence, trainHashtagSequence, trainMwSequence, testTweetSequence, testHashtagSequence, testMwSequence, word2vecDict, trainStartIdx, testStartIdx = loadData({},np.array([]), 40, 0.9, 84)
    print len(trainStartIdx)
    print len(trainTweets)
    print len(testStartIdx)
    print len(testTweets)
    print trainX.shape
    print testX.shape
    print trainY_task.shape
    print testY_task.shape
