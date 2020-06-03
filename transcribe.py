import os
import tensorflow.compat.v1 as tf
import librosa
import numpy as np

import argparse
from magenta.common import tf_utils
from magenta.music import audio_io
import magenta.music as mm
from magenta.models.onsets_frames_transcription import audio_label_data_utils
from magenta.models.onsets_frames_transcription import configs
from magenta.models.onsets_frames_transcription import constants
from magenta.models.onsets_frames_transcription import data
from magenta.models.onsets_frames_transcription import infer_util
from magenta.models.onsets_frames_transcription import train_util
from magenta.music import midi_io
from magenta.music.protobuf import music_pb2
from magenta.music import sequences_lib

def main(input, output, checkpoint_dir):
    model_type = "MAESTRO (Piano)" #@param ["MAESTRO (Piano)", "E-GMD (Drums)"]

    config = configs.CONFIG_MAP['onsets_frames']
    hparams = config.hparams
    hparams.use_cudnn = False
    hparams.batch_size = 1


    examples = tf.placeholder(tf.string, [None])

    dataset = data.provide_batch(
        examples=examples,
        preprocess_examples=True,
        params=hparams,
        is_training=False,
        shuffle_examples=False,
        skip_n_initial_records=0)

    estimator = train_util.create_estimator(
        config.model_fn, checkpoint_dir, hparams)

    iterator = dataset.make_initializable_iterator()
    next_record = iterator.get_next()

    #@title Audio Upload
    to_process = []
    def process(files):
        for fn in files:
            print('**\n\n', fn, '\n\n**')
            with open(fn, 'rb', buffering=0) as f:
                wav_data = f.read()
            example_list = list(
                audio_label_data_utils.process_record(
                wav_data=wav_data,
                ns=music_pb2.NoteSequence(),
                example_id=fn,
                min_length=0,
                max_length=-1,
                allow_empty_notesequence=True))
            assert len(example_list) == 1
            to_process.append(example_list[0].SerializeToString())
            print('Processing complete for', fn)


            sess = tf.Session()

            sess.run([
                tf.initializers.global_variables(),
                tf.initializers.local_variables()
            ])

            sess.run(iterator.initializer, {examples: to_process})

            def transcription_data(params):
                del params
                return tf.data.Dataset.from_tensors(sess.run(next_record))


            input_fn = infer_util.labels_to_features_wrapper(transcription_data)

    #@title Run inference
            prediction_list = list(
                estimator.predict(
                    input_fn,
                    yield_single_examples=False))
            assert len(prediction_list) == 1

    # Ignore warnings caused by pyfluidsynth
            import warnings
            warnings.filterwarnings("ignore", category=DeprecationWarning) 

            sequence_prediction = music_pb2.NoteSequence.FromString(
                prediction_list[0]['sequence_predictions'][0])

            pathname = fn.split('/').pop()
            print('**\n\n', pathname, '\n\n**')
            midi_filename = '{outputs}/{file}.mid'.format(outputs=output,file=pathname)
            midi_io.sequence_proto_to_midi_file(sequence_prediction, midi_filename)

    files = ['{inputs}/{file}'.format(inputs=input, file=file) for file in os.listdir(input)]
    print('the files', files)
    process(files)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument('--checkpoint_dir')
    parser.add_argument('--input')
    parser.add_argument('--output')

    args = parser.parse_args()

    main(args.input, args.output, args.checkpoint_dir)
