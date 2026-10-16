/* Batch mono capture into 20 ms frames. This processor never plays microphone
   samples; the silent output keeps capture running on browsers that require it. */
class TamanitomoVoiceCapture extends AudioWorkletProcessor {
 constructor() { super();this.frame=new Float32Array(Math.round(sampleRate*0.02));this.offset=0; }
 process(inputs) {
  const input=inputs[0]?.[0];
  if(input)for(let i=0;i<input.length;i++) {
   this.frame[this.offset++]=input[i];
   if(this.offset===this.frame.length) {
    this.port.postMessage(this.frame,[this.frame.buffer]);
    this.frame=new Float32Array(Math.round(sampleRate*0.02));this.offset=0;
   }
  }
  return true;
 }
}
registerProcessor('tamanitomo-voice-capture',TamanitomoVoiceCapture);
