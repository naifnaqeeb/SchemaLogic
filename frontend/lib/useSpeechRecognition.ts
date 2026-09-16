"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Reimplemented directly in the browser via the Web Speech API -- React is a much better fit for
// this than the Streamlit version's cross-iframe DOM-injection hack was (see the Streamlit
// build's voice_input.py for what that looked like). Same safety contract as before: normal
// typing must ALWAYS keep working regardless of what happens here. Every browser-API access is
// wrapped in try/catch; on any failure (unsupported browser, permission denied, recognition
// error) this hook just reports `supported: false` or silently resets `listening` -- it never
// throws into the caller, and it never touches the text input directly (the caller decides what
// to do with the transcript via onResult, same separation as before).

interface SpeechRecognitionResultLike {
  results: { [index: number]: { [index: number]: { transcript: string } } };
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultLike) => void) | null;
  start: () => void;
  stop: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function useSpeechRecognition(onResult: (transcript: string) => void) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    setSupported(getSpeechRecognitionConstructor() !== null);
  }, []);

  const toggle = useCallback(() => {
    try {
      if (listening) {
        recognitionRef.current?.stop();
        return;
      }
      const Ctor = getSpeechRecognitionConstructor();
      if (!Ctor) return; // unsupported -- no-op, typing is unaffected either way

      const recognition = new Ctor();
      recognition.lang = "en-IN";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.onstart = () => setListening(true);
      recognition.onend = () => setListening(false);
      recognition.onerror = () => setListening(false);
      recognition.onresult = (event) => {
        try {
          const transcript = event.results[0][0].transcript;
          onResult(transcript);
        } catch {
          // never break typing -- recognized text just doesn't land, that's all
        }
      };
      recognitionRef.current = recognition;
      recognition.start();
    } catch {
      // Web Speech API unavailable/blocked in this context -- silent no-op
    }
  }, [listening, onResult]);

  return { supported, listening, toggle };
}
