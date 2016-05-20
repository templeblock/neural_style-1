import os, re
import numpy as np 
from scandir import scandir

from keras import backend as K
from keras.utils.generic_utils import Progbar
if K._BACKEND == 'theano':
    from theano import tensor as T
else:
    import tensorflow as tf

from utils.imutils import *

########
# Losses
########
def grams(X):
    if K._BACKEND == 'theano':
        samples, c, h, w = K.shape(X)
    else:
        try:
            samples, c, h, w = K.int_shape(X)
        except Exception, e:
            samples, c, h, w = K.shape(X)
        
    X_reshaped = K.reshape(X, (-1, c, h * w))
    X_T = K.permute_dimensions(X_reshaped, (0, 2, 1))
    if K._BACKEND == 'theano':
        X_gram = T.batched_dot(X_reshaped, X_T) / (2. * c * h * w)
    else:
        X_gram = tf.batch_matmul(X_reshaped, X_T) / (2. * c * h * w)

    return X_gram

def frobenius_error(y_true, y_pred):
    loss = K.sum(K.square(y_pred - y_true))

    return loss

def squared_normalized_euclidian_error(y_true, y_pred):
    loss = K.mean(K.square(y_pred - y_true) / 2.) 

    return loss

#######
# Regularizer
#######
def total_variation_error(y, beta=1):
    # Negative stop indices are not currently supported in tensorflow ...
    if K._BACKEND == 'theano':
        a = K.square(y[:, :, 1:, :-1] - y[:, :, :-1, :-1])
        b = K.square(y[:, :, :-1, 1:] - y[:, :, :-1, :-1])
    else:
        samples, c, h, w = K.int_shape(y)
        a = K.square(y[:, :, 1:, :w-1] - y[:, :, :h-1, :w-1])
        b = K.square(y[:, :, :h-1, 1:] - y[:, :, :h-1, :w-1])
    loss = K.sum(K.pow(a + b, beta / 2))

    return loss

##########
# Training
##########
def train_input(input_data, train_iteratee, optimizer, config={}, max_iter=2000):
    losses = {'training_loss': [], 'cv_loss': [], 'best_loss': 1e15}

    wait = 0
    best_input_data = None
    progbar = Progbar(max_iter)
    progbar_values = []
    for i in range(max_iter):
        training_loss, grads_val = train_iteratee([input_data])
        training_loss = training_loss.item(0)
        input_data, config = optimizer(input_data, grads_val, config)

        losses['training_loss'].append(training_loss)
        progbar_values.append(('training_loss', training_loss))

        progbar.update(i + 1, progbar_values)

        if training_loss < losses['best_loss']:
            losses['best_loss'] = training_loss
            best_input_data = np.copy(input_data)
            wait = 0
        else:
            if wait >= 100 and i > max_iter / 2:
                break
            wait +=1

    print("final loss:", losses['best_loss'])
    return best_input_data, losses

def train_weights(input_dir, size, model, train_iteratee, cv_input_dir=None, max_iter=2000, batch_size=4):
    losses = {'training_loss': [], 'cv_loss': [], 'best_loss': 1e15}
    
    best_trainable_weights = model.get_weights()

    need_more_training = True
    wait = 0
    current_iter = 0
    current_epoch = 0
    files = [input_dir + '/' + name for name in os.listdir(input_dir) if len(re.findall('\.(jpg|png)$', name))]
    
    while need_more_training:
        print('Epoch %d, max_iter %d' % (current_epoch + 1, max_iter))
        progbar = Progbar(len(files))
        progbar_values = []

        ims = []
        current_batch = 0
        for dirEntry in scandir(input_dir):
            if not len(re.findall('\.(jpg|png)$', dirEntry.path)):
                continue
            im = load_image(dirEntry.path, size=size)
            ims.append(im)
            if len(ims) >= batch_size:
                ims = np.array(ims)
                training_loss = train_iteratee([ims, True])
                training_loss = training_loss[0].item(0)
                losses['training_loss'].append(training_loss)
                progbar_values.append(('training_loss', training_loss))
                if cv_input_dir != None:
                    cv_loss = train_iteratee([cv_input_dir, False])
                    cv_loss = cv_loss[0].item(0)
                    losses['cv_loss'].append(cv_loss)
                    progbar_values.append(('cv_loss', cv_loss))

                progbar.update((current_batch + 1)* batch_size, progbar_values)

                if training_loss < losses['best_loss']:
                    losses['best_loss'] = training_loss
                    best_trainable_weights = model.get_weights()
                    wait = 0
                else:
                    if wait >= 100 and current_iter > max_iter / 2:
                        break
                    wait +=1

                current_iter += 1
                current_batch += 1
                ims = []

                if current_iter >= max_iter:
                    need_more_training = False
                    break

        current_epoch += 1

    print("final best loss:", losses['best_loss'])
    return best_trainable_weights, losses
