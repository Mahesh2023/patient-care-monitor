// AudioWorklet: forwards mono input blocks to the main thread (no processing
// on the real-time audio thread). Raw audio never leaves the browser.
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("care-tap", Tap);
