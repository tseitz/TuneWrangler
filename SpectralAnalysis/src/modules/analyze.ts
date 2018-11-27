import * as tf from '@tensorflow/tfjs';
import clip from '../assets/INYOURHEAD.mp3';

declare const p5: any;

export default function sketch(s) {
  let song;
  let fft;
  let button;

  s.preload = () => {
    song = s.loadSound(clip);
  }

  s.setup = () => {
    s.createCanvas(256, 256);

    button = s.createButton('toggle');
    button.mousePressed(toggleSong);

    console.log('play');
    song.play();

    fft = new p5.FFT(0.9, 256);

    setTimeout(() => {
      console.log('pause');
      song.pause();
    }, 1000);
  }

  s.draw = () => {
    s.background(0);

    let spectrum = fft.analyze();
    if (spectrum.some((i) => i > 0)) {
      const tensor = tf.tensor2d(spectrum, [64, 4]);
      tensor.print();
    }
    s.noStroke();

    s.translate(s.width / 2, s.height / 2);

    for (var i = 0; i < spectrum.length; i++) {
      var angle = s.map(i, 0, spectrum.length, 0, 360);
      var amp = spectrum[i];
      var r = s.map(amp, 0, 256, 20, 100);
      //fill(i, 255, 255);
      var x = r * s.cos(angle);
      var y = r * s.sin(angle);
      s.stroke(i, 255, 255);
      s.line(0, 0, x, y);
      //vertex(x, y);
      //var y = map(amp, 0, 256, height, 0);
      //rect(i * w, y, w - 2, height - y);
    }
  }

  const toggleSong = () => {
    if (song.isPlaying()) {
      song.pause();
    } else {
      song.play();
    }
  }
}