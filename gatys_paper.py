import os

from keras import backend as K

from vgg19.model_headless import VGG_19_headless_5, get_layer_data

from utils.imutils import (load_images, create_noise_tensor, 
                    dump_as_hdf5, deprocess, save_image,
                    plot_losses)
from utils.lossutils import (frobenius_error, total_variation_error, 
                            grams, norm_l2, train_input
                            )

optimizer = 'lbfgs'
if optimizer == 'lbfgs':
    K.set_floatx('float64') # scipy needs float64 to use lbfgs


dir = os.path.dirname(os.path.realpath(__file__))
vgg19Dir = dir + '/vgg19'
dataDir = dir + '/data'
resultsDir = dataDir + '/output/vgg19'
if not os.path.isdir(resultsDir): 
    os.makedirs(resultsDir)

paintingsDir = dataDir + '/paintings'

channels = 3
width = 600
height = 600
input_shape = (channels, width, height)
batch = 4

print('Loading train images')
X_train = load_images(dataDir + '/overfit', size=(height, width), limit=1, dim_ordering='th', verbose=True)
print("X_train shape:", X_train.shape)

print('Loading painting')
X_train_style = load_images(dataDir + '/paintings', size=(height, width), limit=1, dim_ordering='th', verbose=True)
print("X_train_style shape:", X_train_style.shape)

print('Loading VGG headless 5')
modelWeights = vgg19Dir + '/vgg-19_headless_5_weights.hdf5'
model = VGG_19_headless_5(modelWeights, trainable=False)
layer_dict, layers_names = get_layer_data(model, 'conv_')
print('Layers found:' + ', '.join(layers_names))

input_layer = model.input
style_layers_used = ['conv_1_2', 'conv_2_2', 'conv_3_2', 'conv_3_4', 'conv_4_3']
feat_layers_used = ['conv_3_4', 'conv_4_2', 'conv_4_4']
# before conv_3_2 layers are too "clean" for human perception
# from conv_5_1 layers doesn't hold enough information to rebuild the structure of the photo
style_outputs_layer = [layer_dict[name].output for name in style_layers_used]
feat_outputs_layer = [layer_dict[name].output for name in feat_layers_used]

print('Creating training labels')
predict_style = K.function([input_layer], style_outputs_layer)
train_style_labels = predict_style([X_train_style])
predict_feat = K.function([input_layer], feat_outputs_layer)
train_feat_labels = predict_feat([X_train])

print('Preparing training loss functions')
train_loss_styles = []
for idx, train_style_label in enumerate(train_style_labels):
    train_loss_styles.append(
        frobenius_error(
            grams(train_style_label), 
            grams(style_outputs_layer[idx])
        )
    )

reg_TV = total_variation_error(input_layer, 2)

print('Building white noise images')
input_data = create_noise_tensor(height, width, channels, 'th')

print('Using optimizer: ' + optimizer)
current_iter = 1
for idx, feat_output in enumerate(feat_outputs_layer):
    layer_name_feat = feat_layers_used[idx]
    train_loss_feat = frobenius_error(train_feat_labels[idx], feat_output)
    print('Compiling VGG headless 5 for ' + layer_name_feat + ' feat reconstruction')
    for alpha in [1e2]:
        for beta in [5e0]:
            for gamma in [1e-3]:
                print("alpha, beta, gamma:", alpha, beta, gamma)

                print('Computing train loss')
                tls = [train_loss_style * alpha * 1 / len(train_loss_styles) for train_loss_style in train_loss_styles]
                tlf = [train_loss_feat * beta]
                rtv = reg_TV * gamma
                train_loss =  sum(tls + tlf) + rtv

                print('Computing gradients')
                grads = K.gradients(train_loss, input_layer)
                if optimizer == 'adam':
                    grads = norm_l2(grads)
                inputs = [input_layer]
                outputs = [train_loss, grads] + tlf + tls

                print('Computing iteratee function')
                train_iteratee = K.function(inputs, outputs)

                config = {'learning_rate': 5e-01}
                best_input_data, losses = train_input(input_data, train_iteratee, optimizer, config, max_iter=1000)

                print('Dumping data')
                prefix = str(current_iter).zfill(4)
                suffix = '_alpha' + str(alpha) +'_beta' + str(beta) + '_gamma' + str(gamma)
                filename = prefix + '_gatys_paper_feat' + layer_name_feat + suffix
                dump_as_hdf5(resultsDir + '/' + filename + ".hdf5", best_input_data[0])
                save_image(resultsDir + '/' + filename + '.png', deprocess(best_input_data[0], dim_ordering='th'))
                plot_losses(losses, resultsDir, prefix, suffix)

                current_iter += 1