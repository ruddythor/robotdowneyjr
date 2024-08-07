import sounddevice as sd
import numpy as np
from transformers import SpeechT5HifiGan
import torch
from transformers import GPT2Tokenizer, SpeechT5ForTextToSpeech, SpeechT5Processor, Wav2Vec2Processor, TFWav2Vec2ForCTC
import openai
from openai import OpenAI
from scipy.io.wavfile import write, read
import tensorflow as tf
import soundfile as sf
from datasets import load_dataset
from transformers import GPT2Tokenizer, TFGPT2LMHeadModel
import argparse
import os
import torchaudio
import speechbrain as sb
import tensorflow as tf
import numpy as np
import yaml
import tensorflow as tf
import pyttsx3
import speech_recognition as sr

import sys
# sys.path.append('/content/TensorFlowTTS')


# from speechbrain.pretrained import Tacotron2
# from speechbrain.pretrained import HIFIGAN
import nltk
nltk.download('punkt')

def split_text_into_chunks(text, max_length):
    sentences = nltk.sent_tokenize(text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk + sentence) <= max_length:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


RECORD_SECONDS = 10
SAMPLE_RATE = 16000
def record_audio():
    print("Recording...")
    audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()
    return audio

def save_audio_to_file(filename, audio):
    write(filename, SAMPLE_RATE, audio)

def play_audio_from_file(filename):
    print("Playing...")
    sample_rate, audio = read(filename)
    sd.play(audio, sample_rate)
    sd.wait()

def transcribe_audio(filename):
    processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h")
    model = TFWav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")
    sample_rate, audio = read(filename)
    input_values = processor(audio, sampling_rate=sample_rate, return_tensors="tf").input_values
    logits = model(input_values).logits
    predicted_ids = tf.argmax(logits, axis=-1)
    transcription = processor.decode(predicted_ids[0].numpy())
    return transcription

def speak_response_simple(response):
    engine = pyttsx3.init()
    #engine.save_to_file(response, 'gen_speech.mp3')
    engine.say(response)
    engine.runAndWait()

def speak_response_gtts(response):
    from gtts import gTTS


    # Language in which you want to convert
    language = 'en'

    # Passing the text and language to the engine, 
    # here we have marked slow=False. Which tells 
    # the module that the converted audio should 
    # have a high speed
    myobj = gTTS(text=response, lang=language, slow=False)

    # Saving the converted audio in a mp3 file named
    # welcome 
    myobj.save("response.mp3")

    # Playing the converted file
    os.system("mpg321 response.mp3 &")   
    

def get_voice_input(engine):
    r = sr.Recognizer()
    #mic = sr.Microphone()
    mic = sr.Microphone(device_index=0)
    print("\n***\nEnter your input now, via microphone.")
    # engine.say("I'm listening. Please give your command.")
    speak_response_gtts("I'm listening.")
    engine.runAndWait()
    with mic as source:
        audio = r.listen(source)

    # with open("microphone-results.wav", "wb") as f:
    #   f.write(audio.get_wav_data())
    return r.recognize_whisper(audio)


def speak_response(response, filename):
    processor = SpeechT5Processor.from_pretrained("microsoft/speecht5_tts")
    model = SpeechT5ForTextToSpeech.from_pretrained("microsoft/speecht5_tts")
    vocoder = SpeechT5HifiGan.from_pretrained("microsoft/speecht5_hifigan")

    # load xvector containing speaker's voice characteristics from a dataset
    embeddings_dataset = load_dataset("Matthijs/cmu-arctic-xvectors", split="validation")
    speaker_embeddings = torch.tensor(embeddings_dataset[7306]["xvector"]).unsqueeze(0)

    # Split response into chunks
    max_length = 512  # Adjust this value based on your model's maximum input length
    chunks = split_text_into_chunks(response, max_length)

    all_speech = []
    for chunk in chunks:
        inputs = processor(text=chunk, return_tensors="pt")
        speech = model.generate_speech(inputs["input_ids"], speaker_embeddings, vocoder=vocoder)
        all_speech.append(speech.numpy())

    # Concatenate the waveforms along the time dimension
    final_waveform = np.concatenate(all_speech, axis=-1)

    sf.write(filename, final_waveform, samplerate=16000)
def generate_response_online(prompt):
    # openai.api_key = os.getenv("OPENAI_KEY")
    # openai.base_url = 'http://localhost:11434/v1'

    client = OpenAI(
        base_url="http://192.168.50.235:1234/v1",
        api_key="llama3",
    )
    def get_response(prompt):
        response = client.chat.completions.create(
                # engine="text-davinci-002",
                model="tinyllama",
                # prompt=prompt,
                messages=[
                    {
                        'role': 'system',
                        'content': 'You are a helpful AI assistant who answers questions very succinctly. You always respond very tersely and to the point. You will include NO FORMATTING in your response, and respond as if your reply will be spoken.'
                    },
                    { 
                        'role': 'user',
                        'content': prompt
                    },
                ],
                max_tokens=200,
                # n=1,
                # stop=None,
                # temperature=0.5,
                )

        message = response.choices[0].message.content
        return message


    response = get_response(prompt)
    return response

def generate_speech_local(prompt):

    # Intialize TTS (tacotron2) and Vocoder (HiFIGAN)
    tacotron2 = sb.pretrained.Tacotron2.from_hparams(source="speechbrain/tts-tacotron2-ljspeech", savedir="tmpdir_tts")
    hifi_gan = sb.pretrained.HIFIGAN.from_hparams(source="speechbrain/tts-hifigan-ljspeech", savedir="tmpdir_vocoder")

    # Running the TTS
    mel_output, mel_length, alignment = tacotron2.encode_text(prompt)

    # Running Vocoder (spectrogram-to-waveform)
    waveforms = hifi_gan.decode_batch(mel_output)

    # Save the waverform
    torchaudio.save('offlinesound.wav',waveforms.squeeze(1), 22050)


# Generate a response using GPT-2
def generate_response(prompt):
    # Load pre-trained model and tokenizer
    tokenizer = GPT2Tokenizer.from_pretrained("distilgpt2")
    model = TFGPT2LMHeadModel.from_pretrained("distilgpt2")

    # Encode prompt
    inputs = tokenizer.encode(prompt, return_tensors="tf")
    
    # Generate text
    outputs = model.generate(inputs, max_length=100, num_return_sequences=1, no_repeat_ngram_size=2)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    return response

def main():
    #speak_response("I have finished booting. Ready to accept instructions.", "boot.wav")
    #speak_response("Thinking.", "thinking.wav")

    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()

    if args.offline:

        print("offline mode enabled")
        data, samplerate = sf.read("boot.wav")
        sd.play(data, samplerate)
        sd.wait()
        audio = record_audio()
        save_audio_to_file("recorded_audio.wav", audio)
    
        thinking, samplerate = sf.read("thinking.wav")
        sd.play(thinking, samplerate)
        sd.wait()
        #play_audio_from_file("recorded_audio.wav")a
        #transcription = "What is the future of space travel?"
        #transcription = "How can a ship fly using antigravity?"
        transcription = transcribe_audio("recorded_audio.wav")
        print("Transcription:", transcription)
        
        sd.play(thinking, samplerate)
        sd.wait()
        response = generate_response(transcription)
        print("Hank says:", response)
        speak_response(response, "speech.wav")

        # respond, samplerate = sf.read("speech.wav")
        # sd.play(respond, samplerate)
        # sd.wait()

        generate_speech_local(response)
        respond, samplerate = sf.read("offlinesound.wav")
        sd.play(respond,samplerate)
        sd.wait()

        print("offline mode enabled")
    else:
        # download_models()

        print("online mode enabled")
        #data, samplerate = sf.read("boot.wav")
        #sd.play(data, samplerate)
        #sd.wait()
        engine = pyttsx3.init()

        transcription = get_voice_input(engine)
        print("Transcription:", transcription)

        if True: # 'hank respond' in transcription.lower() or 'hank, respond' in transcription.lower():        
            #sd.play(thinking, samplerate)
            #sd.wait()
            response = generate_response_online(transcription)
            print("Hank says:", response)
            speak_response_gtts(response)
        else:
            print("could not get command.")

        #respond, samplerate = sf.read("speech.wav")
        #sd.play(respond, samplerate)
        #sd.wait()

        #print("Online mode enabled")

if __name__ == "__main__":
    ## while True:
    main()
