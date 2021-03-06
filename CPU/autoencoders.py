from neural_network import NEURAL_NETWORK

import sys
import time     as tm
import math     as mt
import tools    as tl
import numpy    as np
import loader   as ld
import display  as dy
import warnings as wn

# Global parameters
DROPOUT       = False
SPARSITY      = True
PREPROCESSING = False
ANGLE_DRIVEN  = True
AVG_GRADIENT  = False
GRAD_CHECK    = False
DEBUG         = False

class AUTOENCODERS(NEURAL_NETWORK):
    
    def __init__(self, fNeurons, fBatchSize):

        # Mother class initialization
        NEURAL_NETWORK.__init__(self,
                                len(fNeurons),
                                fNeurons,
                                fBatchSize)

        # Regularization terms
        self.mRegu           = 0.
        
        # Dynamic learning rate
        self.mLeakControl    = 0.4
        self.mAlpha          = 0.01
        self.mBeta           = 0.1

        # Sparsity
        self.mSparsityWeight = 1.0
        self.mSparsity       = 0.05

        # Momentum
        self.mMomentum       = [0.1] * (self.mNbLayers-1)
        self.mLambda         = 0.05

        # Dropout scaling
        self.mDropoutScaling = 0.5

        # Activation function
        self.activation_function_initialization()
            
#####################################################################

    def activation_function_initialization(self):
        '''Define an activation function per neurons' layer 
        and the corresponding derived function.'''
        
        for i in xrange(self.mNbLayers-2):
            self.mActivation.append(tl.sigmoid)
            self.mDerived.append(tl.dsigmoid)

        self.mActivation.append(tl.sigmoid_output)
        self.mDerived.append(tl.dsigmoid_output)
        
#####################################################################

    def propagation(self, fInput, fDropout=False):
        '''Propagation of the input (can be a minibatch) throughout
        turning fDropout argument to True. The dropout scaling 
        the neural network. A dropout system can be activated by 
        parameters can be modified in neural network parameters.

        INPUT : Vector or matrix, dropout
        OUPUT : Neurons activation'''
        
        _out = [fInput]

        if fDropout:
            _p = self.mDropoutScaling

        for i in xrange(self.mNbLayers-1):

            _activation  = np.dot(self.mWeights[i], _out[-1])
            _activation += self.mBiases[i]
            _activation  = self.mActivation[i](_activation)
            
            if fDropout:
                _drop = (np.random.rand(*_activation.shape)<_p) / _p
                _activation *= _drop

            _out.append(_activation)

        return _out

#####################################################################
    
    def layer_error(self, fOut, fIn, fSparsity=False):
        '''Compute local error of each layer. Sparsity term can
        be actived by turning fSparsity argument to True.
        Part of backpropagation.

        INPUT  : Output of each layer, mini-batch, sparsity
        OUTPUT : Error vector of each layer'''

        # Last layer local error
        try:
            _err = [-(fIn - fOut[-1]) * self.mDerived[-1](fOut[-1])]
            
        except Warning:
            print sys.exc_info()[1]
            np.savetxt("log/error_dsig.log", self.mDerived(fOut[-1]))
            np.savetxt("log/error_diff.log", (fIn - fOut[-1]))
            sys.exit(-1)

        # Intermediate layer local error
        for i in xrange(1, self.mNbLayers-1):

            try:
                _backprop  = np.dot(self.mWeights[-i].T, _err[i-1])
                
                _dsigmoid  = self.mDerived[-i-1](fOut[-i-1])

                if fSparsity:
                    _sparsity = self.sparsity(fOut[-i-1])

                else:
                    _sparsity = np.zeros(_backprop.shape)

                _err.append((_backprop + _sparsity) * _dsigmoid)

            except Warning:
                print sys.exc_info()[1]
                np.savetxt("log/error_backprop.log", _backprop)
                np.savetxt("log/error_dsigm.log", _dsigmoid)
                np.savetxt("log/error_sparsity.log", _sparsity)
                sys.exit(-1)

        _err.reverse()

        return _err

#####################################################################
    
    def sparsity(self, fOut):
        '''Compute sparsity term for each layer error. Still bring 
        some zero-division problem. Cannot be used correctly with
        dynamic learning rate (angle driven approach) and dropout.
        In fact dropout already implies sparsity.

        INPUT  : Output of a layer
        OUTPUT : Sparsity term'''

        # Average activation of layers' neurons
        _avg = fOut.mean(1, keepdims=True)

        try:
            _sparsity = self.mSparsityWeight * (-self.mSparsity /_avg + (1. -self.mSparsity) / (1. - _avg))

        except Warning:
            print sys.exc_info()[1]
            np.savetxt("log/error_avg.log", _avg)
            sys.exit(-1)
        
        return _sparsity 

#####################################################################
    
    def gradient(self, fErr, fOut):
        '''Compute weights and biases gradient in order to realize
        mini-batch (stochastic, online) gradient descent.

        INPUT  : Error and output vector of each layers
        OUPUT  : Weights and biases gradient'''

        _wGrad = []
        _bGrad = []

        for err, out in zip(fErr, fOut):
            _wGrad.append(np.dot(err, out.T) / self.mBatchSize)
            _bGrad.append(err.mean(1, keepdims=True))
            
        return _wGrad, _bGrad
    
#####################################################################
    
    def variations(self, fWgrad):
        '''Compute weight variations with momentum and 
        regularization L2 terms.

        INPUT  : Weight gradient of each layers
        OUTPUT : Nothing (variations are class variables)'''
        
        for i in xrange(self.mNbLayers-1):
            try:
                self.mVariations[i] *= self.mMomentum[i]
                self.mVariations[i] -= self.mEpsilon[i] * fWgrad[i]
                self.mVariations[i] -= self.mRegu * self.mWeights[i]

            except Warning:
                print sys.exc_info()[1]

                print "Layer :", i
                print "Momentum :", self.mMomentum[i]
                print "Learning rate :", self.mEpsilon[i]

                np.savetxt("log/error_Weight.log", self.mWeights[i])
                np.savetxt("log/error_Grad.log", fWgrad[i])
                
                sys.exit(-1)

#####################################################################

    def angle_driven_approach(self, fWgrad):
        '''Dynamic learning rate based on angle driven approach.
        Teta correspond to the angle between the previous variation
        and the current gradient.

        From L.W. Chan - An adaptive training algorithm for back...

        INPUT  : Weight gradient (variation is class variable)
        OUTPUT : Nothing 

        Epsilon and momentum are modified in class'''
        
        for i in xrange(self.mNbLayers - 1):

            _var  = self.mVariations[i]
            _grad = fWgrad[i]
        
            # Angle between previous update and current gradient
            try:
                _teta  = np.sum(-_grad * _var)
                _teta /= np.linalg.norm(_grad)
                _teta /= np.linalg.norm(_var)

            except Warning:
                print sys.exc_info()[1]

                print "Iteration :", i
                
                print "Gradient norm :", np.linalg.norm(_grad)
                np.savetxt("log/error_grad.log", _grad)

                print "Variation norm :", np.linalg.norm(_var)
                np.savetxt("log/error_var.log", _var)

                sys.exit(-1)                
                
        
            # Learning rate update
            self.mEpsilon[i] *= (1 + 0.5 * _teta)
            self.mEpsilon[i]  = max(min(self.mEpsilon[i],1),-1)
            
            # Momentum update
            try:
                self.mMomentum[i]  = self.mLambda * self.mEpsilon[i]
                self.mMomentum[i] *= np.linalg.norm(_grad)
                self.mMomentum[i] /= np.linalg.norm(_var)
                self.mMomentum[i]  = max(min(self.mMomentum[i],1),-1)
                    
            except Warning:
                print sys.exc_info()[1]

                print "Iteration :", i
                
                print "Momentum :", self.mMomentum
                print "Learning Rate :", self.mEpsilon

                print "Gradient norm :", np.linalg.norm(_grad)
                np.savetxt("log/error_grad.log", _grad)
                
                print "Variation norm :", np.linalg.norm(_var)
                np.savetxt("log/error_var.log", _var)

                sys.exit(-1)

#####################################################################

    def average_gradient_approach(self, fWgrad):
        '''Dynamic learning rate based on average gradient approach

        from Yan LeCun - Efficient backprop.
        INPUT  : Weights gradient
        OUTPUT : Nothing
        
        Epsilon is modified in class'''

        aga = self.average_gradient_approach.__func__
        if not hasattr(aga, "_avg"):
            aga._avg = [np.zeros(self.mWeights[i].shape)
                        for i in xrange(self.mNbLayers - 1)]

        for i in xrange(self.mNbLayers - 1):

            aga._avg[i] *= (1 - self.mLeakControl)
            aga._avg[i] += self.mLeakControl * fWgrad[i]

            self.mEpsilon[i] += self.mAlpha * self.mEpsilon[i] * (self.mBeta * np.linalg.norm(aga._avg[i]) - self.mEpsilon[i])

            self.mEpsilon[i]  = max(min(self.mEpsilon[i],1),-1)
            
#####################################################################
    
    # Update weights and biases parameters with gradient descent
    def update(self, fBgrad):
        '''Stochastic (online, mini-batch) gradient descent.

        Weight variations, weights and biases are class variables.

        INPUT  : Biases gradient
        OUTPUT : Nothing'''
        
        for i in xrange(self.mNbLayers-1):

            # Update weights
            self.mWeights[i] += self.mVariations[i]

            # Update biases
            self.mBiases[i]  += self.mEpsilon[i] * fBgrad[i]
    
#####################################################################
    
    # Algorithm which train the neural network to reduce cost
    def train(self, fImgs, fLbls, fIterations, fName):
        '''Training algorithm. Can evolved according to your need.

        INPUT  : Images set, labels set (None for autoencoders),
                 number of iterations before stopping, name for save
        OUTPUT : Nothing'''

        if PREPROCESSING:
            fImgs, _key = ld.normalization(fName, fImgs)

        print "Training...\n"
        
        _gcost = []
        _gtime = []
        
        _done  = fIterations

        for i in xrange(fIterations):

            _gtime.append(tm.time())
            _gcost.append(0)

            for j in xrange(self.mCycle):
                
                _trn, _tst = self.cross_validation(j, fImgs)

                for k in xrange(len(_trn) / self.mBatchSize):

                    if DEBUG:
                        print "Learning rates :", self.mEpsilon
                        print "Momentums :", self.mMomentum
                    
                    # Inputs and labels batch
                    _in  = self.build_batch(k, _trn)

                    # Activation propagation
                    _out = self.propagation(_in, DROPOUT)

                    # Local error for each layer
                    _err = self.layer_error(_out, _in, SPARSITY)
        
                    # Gradient for stochastic gradient descent    
                    _wGrad, _bGrad = self.gradient(_err, _out)
                    
                    # Gradient checking
                    if GRAD_CHECK:
                        print "Gradient checking ..."
                        self.gradient_checking(_in,_in,_wGrad,_bGrad)

                    # Adapt learning rate
                    if (i > 0 or j > 0 or k > 0) and ANGLE_DRIVEN:
                        self.angle_driven_approach(_wGrad)

                    # Weight variations
                    self.variations(_wGrad)
                    
                    # Update weights and biases
                    self.update(_bGrad)

                    # Adapt learning rate
                    if AVG_GRADIENT:
                        self.average_gradient_approach(_wGrad)
                    
                # Evaluate the network
                _cost = self.evaluate(_tst)    
                _gcost[i] += _cost

                if DEBUG:
                    print "Cost :", _cost

            # Iteration information
            _gtime[i] = tm.time() - _gtime[i]
            print "Iteration {0} in {1}s".format(i, _gtime[i])    

            # Global cost for one cycle
            _gcost[i] /= self.mCycle
            print "Cost of iteration : {0}".format(_gcost[i])

            # Parameters
            print "Epsilon {0} Momentum {1}\n".format(self.mEpsilon,
                                                      self.mMomentum)
            
            # Stop condition
            if i > 0 and abs(_gcost[i-1] - _gcost[i]) < 0.001:
                _done = i + 1
                break

            elif self.mStop:
                _done = i + 1
                break
            
        dy.plot(xrange(_done), _gcost, fName, "_cost.png")
        dy.plot(xrange(_done), _gtime, fName, "_time.png")

        if fName is not None:
            self.save_output(fName, "train", fImgs)
        
#####################################################################

    def evaluate(self, fTests):
        '''Evaluate the network at a given iteration. In fact,
        train set is split in 2 by cross-validation. One part is 
        used for training, the other part for evaluation and error
        calculation.

        INPUT  : Test set from training set
        OUTPUT : Current error'''
        
        _out  = self.propagation(fTests.T)
            
        return self.error(_out[-1], fTests.T) / len(fTests)
        
#####################################################################

    # Test the neural network over a test set
    def test(self, fImgs, fLbls, fName):
        '''Neural network testing after training.

        INPUT  : Images set, labels set (None for autoencoders),
                 name for save.
        OUTPUT : Nothing'''

        if PREPROCESSING:
            fImgs, _key = ld.normalization(fName, fImgs)
        
        print "Testing the neural networks..."

        _out   = self.propagation(fImgs.T)
        _cost  = self.error(_out[-1], fImgs.T) / len(fImgs)

        print "Cost {0}\n".format(_cost)

        # Save output in order to have a testset for next layers
        if fName is not None:
            self.save_output(fName, "test", fImgs)

        # Displaying the results
        if PREPROCESSING:
            _decrypt = np.dot(_out[-1],_key.T)
            dy.display(fName, "out", fImgs, _decrypt.T)

        else:
            dy.display(fName, "out", fImgs, _out[-1].T)

        # Approximated vision of first hidden layer neurons
        dy.display(fName, "neurons", self.neurons_vision())
