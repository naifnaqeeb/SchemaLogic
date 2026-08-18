"""Decorative "+" attach icon + functional voice-to-text mic icon, rendered next to the pinned
chat_input bar. Streamlit's native st.chat_input doesn't expose any way to inject content INSIDE
its own pill (it's always full-width, always pinned to the page bottom, ignores column layout --
confirmed empirically earlier this build), so this renders a small, isolated JS component
(st.components.v1.html) that reaches into the PARENT document and adds two floating buttons
positioned next to it, rather than trying to modify the widget itself.

Safety contract (explicit requirement): normal typing in the real chat_input must ALWAYS keep
working, no matter what happens here. This is enforced structurally, not just by convention:
  - The component runs in its own sandboxed iframe -- a JS exception in here cannot propagate to
    or crash the outer Streamlit app's own script-run/rerun cycle.
  - Every DOM/API access that reaches into the parent page or into the Web Speech API is wrapped
    in try/catch; on ANY failure the mic/attach buttons simply don't appear or don't respond --
    they never touch, block, or intercept the textarea's own normal keyboard input path.
  - Re-running this component (which happens on every Streamlit rerun) is idempotent -- it checks
    for its own marker element before injecting anything a second time, so reruns never pile up
    duplicate floating buttons.

Voice-to-text writes the recognized transcript INTO the chat_input's textarea and stops there --
it does NOT auto-submit. The citizen reviews/edits and presses Enter or the native send button
themselves, same as normal typed text; misrecognized speech is never silently sent.
"""

from __future__ import annotations

import streamlit as st

_COMPONENT_HTML = """
<script>
(function() {
  try {
    var doc = window.parent.document;
    if (doc.getElementById('sl-input-extras')) { return; }  // already injected -- reruns are idempotent

    var style = doc.createElement('style');
    style.textContent = [
      '#sl-input-extras { position: fixed; z-index: 1000; display: flex; gap: 0.35rem; align-items: center; pointer-events: none; }',
      '#sl-input-extras button { pointer-events: auto; }',
      '#sl-attach-btn, #sl-mic-btn {',
      '  width: 2.1rem; height: 2.1rem; border-radius: 50%; border: none; cursor: pointer;',
      '  display: flex; align-items: center; justify-content: center; font-size: 1.05rem;',
      '  background: transparent; color: #6B7280; transition: background 0.15s ease;',
      '}',
      '#sl-attach-btn:hover, #sl-mic-btn:hover { background: rgba(15,27,61,0.06); }',
      '#sl-mic-btn.sl-listening { color: #C0524B; }',
      '#sl-mic-btn.sl-unsupported { opacity: 0.35; cursor: default; }'
    ].join('\\n');
    doc.head.appendChild(style);

    var container = doc.createElement('div');
    container.id = 'sl-input-extras';
    container.innerHTML =
      '<button id="sl-attach-btn" type="button" title="Attachments not available yet">+</button>' +
      '<button id="sl-mic-btn" type="button" title="Voice input">\\u{1F3A4}</button>';
    doc.body.appendChild(container);

    function positionExtras() {
      try {
        var chatInput = doc.querySelector('[data-testid="stChatInput"]');
        if (!chatInput) { return; }
        var rect = chatInput.getBoundingClientRect();
        // Grouped together just left of the native send button -- Streamlit's chat_input has no
        // left-padding region we can safely use without overlapping the typing area itself, so
        // both icons sit on the right (a deliberate deviation from the reference design's
        // left-attach/right-mic split -- see the build report for why).
        container.style.left = (rect.right - 132) + 'px';
        container.style.top = (rect.top + rect.height / 2 - 17) + 'px';
      } catch (e) { /* never let a layout hiccup here touch the main app */ }
    }
    positionExtras();
    try {
      var RO = doc.defaultView.ResizeObserver;
      if (RO) { new RO(positionExtras).observe(doc.body); }
    } catch (e) {}
    doc.defaultView.addEventListener('resize', positionExtras);
    setInterval(positionExtras, 800);  // Streamlit reruns can shift the input; cheap periodic re-sync

    var micBtn = doc.getElementById('sl-mic-btn');
    var SpeechRecognition = doc.defaultView.webkitSpeechRecognition || doc.defaultView.SpeechRecognition;
    if (!SpeechRecognition) {
      micBtn.classList.add('sl-unsupported');
      micBtn.title = 'Voice input not supported in this browser';
    } else {
      var recognizing = false;
      var recognition = null;
      micBtn.addEventListener('click', function() {
        try {
          if (recognizing) { if (recognition) { recognition.stop(); } return; }
          recognition = new SpeechRecognition();
          recognition.lang = 'en-IN';
          recognition.interimResults = false;
          recognition.maxAlternatives = 1;
          recognition.onstart = function() { recognizing = true; micBtn.classList.add('sl-listening'); };
          recognition.onend = function() { recognizing = false; micBtn.classList.remove('sl-listening'); };
          recognition.onerror = function() { recognizing = false; micBtn.classList.remove('sl-listening'); };
          recognition.onresult = function(event) {
            try {
              var transcript = event.results[0][0].transcript;
              var textarea = doc.querySelector('[data-testid="stChatInputTextArea"]');
              if (!textarea) { return; }
              // React-controlled inputs ignore a plain `.value = ...` assignment -- it has to go
              // through the native setter so React's own change tracking picks it up, same as if
              // the citizen had typed it.
              var setter = Object.getOwnPropertyDescriptor(doc.defaultView.HTMLTextAreaElement.prototype, 'value').set;
              setter.call(textarea, transcript);
              textarea.dispatchEvent(new Event('input', { bubbles: true }));
              textarea.focus();
              // Deliberately does NOT submit -- the citizen reviews/edits and sends it themselves,
              // exactly like any other typed message.
            } catch (e) { /* never break typing -- recognized text just doesn't land, that's all */ }
          };
          recognition.start();
        } catch (e) { /* Web Speech API unavailable/blocked in this context -- silent no-op */ }
      });
    }
  } catch (e) { /* whole component is best-effort -- typing in the real input is never affected */ }
})();
</script>
"""


def render_input_extras() -> None:
    """Zero-height component -- it never occupies layout space itself; its content escapes into
    the parent document via JS and positions itself with fixed CSS, as described above."""
    st.components.v1.html(_COMPONENT_HTML, height=0)
