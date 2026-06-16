const state = {
  backend: null,
  settings: null,
  activeTab: 'General',
  dictData: { name: 'default', description: '', substitutions: {}, macros: {}, voice_commands: {} },
  audioDevices: [],
  availableDictionaries: [],
  dictationLog: [],
  dictSubTab: 'Vocabulary', // 'Vocabulary' | 'Templates'
  expandedMacro: null,
  expandedSections: {
    during: false,
    after: false,
    symbols: false
  },
  // Engine Console state
  engineLog: [],
  engineLogLastIndex: -1,
  engineLogPollTimer: null,
  engineLogAutoScroll: true,
  confirmWizardModal: null
};

window.toggleSection = function(name) {
  state.expandedSections[name] = !state.expandedSections[name];
  render();
};

function rgbToHex(arr) {
  if (!arr || arr.length < 3) return "#ffffff";
  const r = arr[0].toString(16).padStart(2, '0');
  const g = arr[1].toString(16).padStart(2, '0');
  const b = arr[2].toString(16).padStart(2, '0');
  return `#${r}${g}${b}` ;
}

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b, 255];
}

function updateSetting(key, value) {
  state.settings[key] = value;
}
function updateSettingAndRender(key, value) {
  state.settings[key] = value;
  render();
}

function renderGeneralTab() {
  const s = state.settings;
  const devs = state.audioDevices.map(d => `
    <option value="${d.index}" ${s.audio_device_index === d.index ? 'selected' : ''}>${d.name}</option>
  `).join('');

  const volumeVal = s.sound_volume !== undefined ? s.sound_volume : 0.5;

  return `
    <div class="card">
      <div class="form-group">
        <label class="label">Microphone Device</label>
        <select class="input-field" onchange="updateSettingAndRender('audio_device_index', parseInt(this.value))">
          <option value="-1" ${s.audio_device_index === null || s.audio_device_index === -1 ? 'selected' : ''}>Default System Device</option>
          ${devs}
        </select>
      </div>
      <div class="form-group" style="margin-top: 24px;">
        <label class="label">Language Lock</label>
        <select class="input-field" onchange="updateSettingAndRender('language_lock', this.value)">
          <option value="" ${!s.language_lock ? 'selected' : ''}>Auto-detect</option>
          <option value="en" ${s.language_lock === 'en' ? 'selected' : ''}>English</option>
          <option value="pt" ${s.language_lock === 'pt' ? 'selected' : ''}>Portuguese</option>
          <option value="es" ${s.language_lock === 'es' ? 'selected' : ''}>Spanish</option>
          <option value="fr" ${s.language_lock === 'fr' ? 'selected' : ''}>French</option>
          <option value="de" ${s.language_lock === 'de' ? 'selected' : ''}>German</option>
          <option value="it" ${s.language_lock === 'it' ? 'selected' : ''}>Italian</option>
          <option value="nl" ${s.language_lock === 'nl' ? 'selected' : ''}>Dutch</option>
          <option value="ja" ${s.language_lock === 'ja' ? 'selected' : ''}>Japanese</option>
          <option value="zh" ${s.language_lock === 'zh' ? 'selected' : ''}>Chinese</option>
          <option value="ko" ${s.language_lock === 'ko' ? 'selected' : ''}>Korean</option>
          <option value="ru" ${s.language_lock === 'ru' ? 'selected' : ''}>Russian</option>
        </select>
        <p style="font-size: 12px; color: var(--text-muted); margin-top: 6px;">Force Whisper to transcribe in this language. Prevents language switching mid-sentence.</p>
      </div>
      
      <div class="form-group" style="margin-top: 24px;">
        <label class="label">Whisper Model</label>
        <select class="input-field" onchange="updateSettingAndRender('whisper_model_size', this.value)">
          <option value="tiny" ${s.whisper_model_size === 'tiny' ? 'selected' : ''}>Tiny (fastest)</option>
          <option value="base" ${s.whisper_model_size === 'base' ? 'selected' : ''}>Base</option>
          <option value="small" ${s.whisper_model_size === 'small' ? 'selected' : ''}>Small</option>
          <option value="medium" ${s.whisper_model_size === 'medium' ? 'selected' : ''}>Medium (recommended)</option>
          <option value="large" ${s.whisper_model_size === 'large' ? 'selected' : ''}>Large (slowest)</option>
        </select>
      </div>
      
      <div class="form-group" style="margin-top: 24px; display: flex; flex-direction: column; gap: 16px;">
        <div class="flex-between">
          <span class="label" style="margin:0;">Play Sounds</span>
          <label class="toggle-switch">
            <input type="checkbox" ${s.sound_enabled ? 'checked' : ''} onchange="updateSettingAndRender('sound_enabled', this.checked)">
            <span class="slider"></span>
          </label>
        </div>
        
        <div>
          <label class="label" style="font-size: 11px;">Sound Volume</label>
          <div style="display: flex; gap: 16px; align-items: center;">
            <input type="range" class="range-slider" min="0" max="1" step="any" value="${volumeVal}" 
                   oninput="updateSetting('sound_volume', parseFloat(this.value)); this.nextElementSibling.value=Math.round(this.value * 100) + '%'" style="flex:1;">
            <input type="text" class="input-field" style="width: 80px; text-align: center; padding: 8px;" readonly value="${Math.round(volumeVal * 100)}%">
          </div>
        </div>
      </div>
      
      <div class="flex-between" style="margin-top: 24px;">
        <span class="label" style="margin:0;">Enable Dictation Log</span>
        <label class="toggle-switch">
          <input type="checkbox" ${s.dictation_log_enabled ? 'checked' : ''} onchange="updateSettingAndRender('dictation_log_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
    </div>
    
    <div class="card">
      <div class="form-group">
        <label class="label">Min Recording Seconds</label>
        <div style="display: flex; gap: 16px; align-items: center;">
          <input type="range" class="range-slider" min="0" max="60" step="any" value="${s.min_recording_seconds}" 
                 oninput="updateSetting('min_recording_seconds', parseFloat(this.value)); this.nextElementSibling.value=Number(this.value).toFixed(2)" style="flex:1;">
          <input type="number" class="input-field" style="width: 80px;" min="0" step="0.1" value="${Number(s.min_recording_seconds).toFixed(2)}"
                 onchange="updateSetting('min_recording_seconds', parseFloat(this.value)); this.previousElementSibling.value=this.value">
        </div>
      </div>
      
      <div class="form-group" style="margin-top: 24px;">
        <label class="label">Silence to Stop (seconds)</label>
        <div style="display: flex; gap: 16px; align-items: center;">
          <input type="range" class="range-slider" min="0" max="60" step="any" value="${s.silence_seconds_to_stop}"
                 oninput="updateSetting('silence_seconds_to_stop', parseFloat(this.value)); this.nextElementSibling.value=Number(this.value).toFixed(2)" style="flex:1;">
          <input type="number" class="input-field" style="width: 80px;" min="0" step="0.1" value="${Number(s.silence_seconds_to_stop).toFixed(2)}"
                 onchange="updateSetting('silence_seconds_to_stop', parseFloat(this.value)); this.previousElementSibling.value=this.value">
        </div>
        <p style="font-size: 12px; color: var(--text-muted); margin-top: 6px;">The duration of silence in seconds that automatically ends recording. Set to 0.0 to disable auto-stop (stop manually using your shortcut or stop wake word).</p>
      </div>
      
      <div class="form-group" style="margin-top: 24px;">
        <label class="label">Commit Window (seconds)</label>
        <div style="display: flex; gap: 16px; align-items: center;">
          <input type="range" class="range-slider" min="0" max="60" step="any" value="${s.commit_window_seconds}"
                 oninput="updateSetting('commit_window_seconds', parseFloat(this.value)); this.nextElementSibling.value=Number(this.value).toFixed(2)" style="flex:1;">
          <input type="number" class="input-field" style="width: 80px;" min="0" step="0.1" value="${Number(s.commit_window_seconds).toFixed(2)}"
                 onchange="updateSetting('commit_window_seconds', parseFloat(this.value)); this.previousElementSibling.value=this.value">
        </div>
        <p style="font-size: 12px; color: var(--text-muted); margin-top: 6px;">The duration of the post-paste listening window for capturing action words (like "send" or "enter"). Set to 0.0 to return directly to idle after pasting.</p>
      </div>
    </div>

    <div class="card">
      <div class="form-group">
        <label class="label">Whisper Initial Prompt</label>
        <textarea class="input-field" rows="3" style="resize: vertical; font-family: inherit; line-height: 1.4;" onchange="updateSettingAndRender('whisper_initial_prompt', this.value)">${s.whisper_initial_prompt || ''}</textarea>
        <p style="font-size: 12px; color: var(--text-muted); margin-top: 6px;">Initial style/vocabulary prompt for Whisper. Priming it with mixed English and Portuguese sentences enables seamless multilingual code-switching.</p>
      </div>
    </div>
  `;
}

// Key catcher
window.captureKey = function(e) {
  e.preventDefault();
  let keys = [];
  if (e.ctrlKey) keys.push("ctrl");
  if (e.shiftKey) keys.push("shift");
  if (e.altKey) keys.push("alt");
  if (e.metaKey) keys.push("meta");
  
  let key = e.key.toLowerCase();
  if (key === ' ') key = 'space';
  if (!['control', 'shift', 'alt', 'meta'].includes(key)) {
    keys.push(key);
  }
  e.target.value = keys.join("+");
  const event = new Event('change', { bubbles: true });
  e.target.dispatchEvent(event);
};

window.updateDictionaryKeybind = function(dictName, bind) {
  if (!state.settings.dictionary_keybinds) state.settings.dictionary_keybinds = {};
  if (bind.trim() === "") {
    delete state.settings.dictionary_keybinds[dictName];
  } else {
    state.settings.dictionary_keybinds[dictName] = bind;
  }
  render();
};

window.switchTab = function(tabName) {
  state.activeTab = tabName;
  render();
};

function renderKeybindsTab() {
  const s = state.settings;
  const binds = [
    { key: 'keybind_toggle', label: 'Start and Stop Dictation', desc: 'Start/stop recording' },
    { key: 'keybind_ptt', label: 'Push-to-Talk', desc: 'Hold to record, release to stop' },
    { key: 'keybind_paste_last_dictation', label: 'Paste Last Dictation', desc: 'Re-paste the last transcript' },
    { key: 'keybind_cancel', label: 'Cancel Dictation', desc: 'Discard current recording' },
  ];
  let html = '';
  binds.forEach(b => {
    html += `
      <div class="card" style="margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">${b.label}</div>
            <div style="font-size: 12px; color: var(--text-muted);">${b.desc}</div>
          </div>
          <div style="width: 220px;">
            <input class="input-field" style="text-align: center; font-family: monospace; font-size: 13px;"
                   value="${s[b.key] || ''}"
                   placeholder="Click and press keys"
                   onkeydown="captureKey(event); updateSetting('${b.key}', this.value)">
          </div>
        </div>
      </div>
    `;
  });
  
  html += `
    <div class="card" style="margin-top: 24px; display: flex; justify-content: space-between; align-items: center; padding: 18px 24px;">
      <div>
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">Voice Activation</div>
        <div style="font-size: 12px; color: var(--text-muted);">Configure voice wake words to start and stop dictation hands-free</div>
      </div>
      <button class="btn btn-secondary" style="padding: 8px 20px; font-size: 13px;" onclick="switchTab('Voice Activation')">Configure</button>
    </div>
  `;
  
  return html;
}

function renderColorsTab() {
  const s = state.settings;
  const colors = [
    { key: 'color_idle', label: 'Idle Color', desc: 'Resting state; dictation is ready.' },
    { key: 'color_recording', label: 'Recording Color', desc: 'Active recording; capturing audio.' },
    { key: 'color_processing', label: 'Processing Color', desc: 'Whisper transcription is running.' },
    { key: 'color_commit_waiting', label: 'Commit Waiting Color', desc: 'Waiting for voice action words (if enabled).' },
    { key: 'color_error', label: 'Error / Cancel Color', desc: 'Dictation was cancelled or encountered an error.' },
  ];

  let html = `<div class="card" style="display: flex; flex-direction: column; gap: 20px; max-width: 600px;">`;
  colors.forEach((c, idx) => {
    const isLast = idx === colors.length - 1;
    const borderStyle = isLast ? '' : 'border-bottom: 1px solid var(--border-light); padding-bottom: 16px;';
    html += `
      <div class="form-group flex-between" style="margin:0; ${borderStyle}">
        <div>
          <label class="label" style="margin:0; font-size: 13px;">${c.label}</label>
          <span style="font-size: 11px; color: var(--text-muted);">${c.desc}</span>
        </div>
        <input type="color" class="color-picker" value="${rgbToHex(s[c.key])}" 
               onchange="updateSettingAndRender('${c.key}', hexToRgb(this.value))">
      </div>
    `;
  });
  html += `</div>`;
  return html;
}

// Capitalization helper
window.capitalizePhrase = function(phrase) {
  if (!phrase) return "";
  return phrase
    .split(",")
    .map(p => {
      return p.trim().split(/\s+/).map(w => {
        if (!w) return "";
        return w.charAt(0).toUpperCase() + w.slice(1);
      }).join(" ");
    })
    .filter(p => p)
    .join(", ");
};

window.isSymbolOrFormatting = function(trigger, replacement) {
  if (!replacement) return false;
  if (replacement.includes('\n') || replacement.includes('\t')) return true;
  const cleanRepl = replacement.trim();
  if (cleanRepl.length === 1 && !/[a-zA-Z0-9]/.test(cleanRepl)) return true;
  if (['==', '===', '!=', '->', '=>', '→', '- '].includes(cleanRepl)) return true;
  const symbolTriggers = [
    'open paren', 'close paren', 'open bracket', 'close bracket', 'open brace', 'close brace',
    'arrow right', 'equals sign', 'double equals', 'triple equals', 'not equals',
    'asterisk', 'forward slash', 'backslash', 'dash', 'hyphen', 'underscore',
    'colon', 'semicolon', 'bullet point', 'open quote', 'close quote', 'single quote',
    'ampersand', 'percent sign', 'dollar sign', 'pound sign', 'at sign',
    'less than sign', 'greater than sign', 'pipe symbol', 'tilde symbol', 'backtick',
    'new paragraph', 'new line'
  ];
  if (symbolTriggers.includes(trigger.toLowerCase())) return true;
  return false;
};

// Profiles Section
window.onActiveDictionaryChange = function(name) {
  state.settings.active_dictionary = name;
  state.backend.load_dictionary(name, (dict_json) => {
    state.dictData = JSON.parse(dict_json);
    if (!state.dictData.substitutions) state.dictData.substitutions = {};
    if (!state.dictData.macros) state.dictData.macros = {};
    if (!state.dictData.voice_commands) state.dictData.voice_commands = {};
    
    // Migrate select_all / delete_all to phase: "after" if they exist
    for (const [phrase, cmd] of Object.entries(state.dictData.voice_commands)) {
      if (cmd.action === 'key' && cmd.keys) {
        if (cmd.keys.includes('a') && cmd.phase === 'during') {
          cmd.phase = 'after';
        }
      }
    }
    
    render();
  });
};

window.addNewProfile = function() {
  const name = prompt("Enter new dictionary profile name:");
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed) {
    alert("Dictionary profile name cannot be empty.");
    return;
  }
  const sanitized = trimmed.replace(/[^a-zA-Z0-9_\- ]/g, "").replace(/\s+/g, "_").toLowerCase();
  if (!sanitized) {
    alert("Invalid dictionary profile name.");
    return;
  }
  if (state.availableDictionaries.includes(sanitized)) {
    alert("A dictionary profile with this name already exists.");
    return;
  }
  
  const defaultProfile = {
    name: trimmed,
    description: `Custom dictionary profile for ${trimmed}`,
    extends: "default",
    substitutions: {},
    macros: {},
    voice_commands: {}
  };
  
  state.backend.save_dictionary(sanitized, JSON.stringify(defaultProfile, null, 4));
  state.availableDictionaries.push(sanitized);
  state.settings.active_dictionary = sanitized;
  window.onActiveDictionaryChange(sanitized);
};

window.deleteSubGroup = function(subType, triggersJson) {
  const triggers = JSON.parse(triggersJson);
  triggers.forEach(t => {
    delete state.dictData[subType][t];
    delete state.dictData[subType][t.toLowerCase()];
  });
  render();
};

window.addSubGroup = function(subType) {
  let phraseInputId = 'new_vocab_phrase';
  let replInputId = 'new_vocab_repl';
  let targetType = subType;
  if (subType === 'macros') {
    phraseInputId = 'new_temp_phrase';
    replInputId = 'new_temp_repl';
  } else if (subType === 'symbols') {
    phraseInputId = 'new_symbol_phrase';
    replInputId = 'new_symbol_repl';
    targetType = 'substitutions';
  }
  const phraseInput = document.getElementById(phraseInputId);
  const replInput = document.getElementById(replInputId);
  if (!phraseInput || !replInput) return;
  const phrases = phraseInput.value.split(",")
    .map(t => window.capitalizePhrase(t))
    .filter(t => t);
  const repl = replInput.value.trim();
  if (phrases.length === 0 || !repl) return;
  
  phrases.forEach(p => {
    state.dictData[targetType][p] = repl;
  });
  phraseInput.value = '';
  replInput.value = '';
  render();
};

window.updateSubGroupTriggers = function(subType, triggersJson, newTriggersStr) {
  const oldTriggers = JSON.parse(triggersJson);
  const newTriggers = newTriggersStr.split(",")
    .map(t => window.capitalizePhrase(t))
    .filter(t => t);
    
  if (newTriggers.length === 0) {
    render();
    return;
  }
  
  const val = state.dictData[subType][oldTriggers[0]] !== undefined ? 
              state.dictData[subType][oldTriggers[0]] : '';
              
  oldTriggers.forEach(t => {
    delete state.dictData[subType][t];
    delete state.dictData[subType][t.toLowerCase()];
  });
  
  newTriggers.forEach(t => {
    state.dictData[subType][t] = val;
  });
  render();
};

window.updateSubGroupValue = function(subType, triggersJson, newVal) {
  const triggers = JSON.parse(triggersJson);
  newVal = newVal.trim();
  
  triggers.forEach(t => {
    state.dictData[subType][t] = newVal;
  });
  render();
};

window.deleteVoiceCommandItem = function(phrase) {
  delete state.dictData.voice_commands[phrase];
  delete state.dictData.voice_commands[phrase.toLowerCase()];
  render();
};

window.addVoiceCommandItem = function(phase) {
  const triggerEl = document.getElementById(`new_vc_${phase}_trigger`);
  const typeEl = document.getElementById(`new_vc_${phase}_type`);
  if (!triggerEl || !typeEl) return;
  
  const rawPhrase = triggerEl.value.trim();
  if (!rawPhrase) return;
  
  const phrase = window.capitalizePhrase(rawPhrase);
  const type = typeEl.value;
  
  delete state.dictData.voice_commands[phrase];
  delete state.dictData.voice_commands[phrase.toLowerCase()];
  
  if (phase === 'after') {
    if (type === 'submit') {
      state.dictData.voice_commands[phrase] = {
        phase: "after",
        action: "submit"
      };
    } else if (type === 'select_all') {
      state.dictData.voice_commands[phrase] = {
        phase: "after",
        action: "key",
        keys: ["ctrl", "a"]
      };
    } else if (type === 'delete_all') {
      state.dictData.voice_commands[phrase] = {
        phase: "after",
        action: "key",
        keys: ["ctrl", "a", "backspace"]
      };
    }
  } else {
    // during phase
    state.dictData.voice_commands[phrase] = {
      phase: "during",
      action: "transform",
      type: type
    };
  }
  
  triggerEl.value = '';
  render();
};

window.setDictSubTab = function(tab) {
  state.dictSubTab = tab;
  render();
};

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderDictionaryTab() {
  const activeDict = state.settings.active_dictionary || 'Default';
  
  const dictOptions = state.availableDictionaries.map(d => `
    <option value="${d}" ${d === activeDict ? 'selected' : ''}>${d}</option>
  `).join('');

  const binds = state.settings.dictionary_keybinds || {};
  const currentBind = binds[activeDict] || '';

  if (state.dictSubTab !== 'Vocabulary' && state.dictSubTab !== 'Templates') {
    state.dictSubTab = 'Vocabulary';
  }

  const subTabs = ['Vocabulary', 'Templates'];
  const subTabsHtml = subTabs.map(t => `
    <button class="btn" style="margin-right: 8px; background: ${state.dictSubTab === t ? 'var(--accent)' : 'transparent'}; border: 1px solid var(--accent); color: ${state.dictSubTab === t ? '#fff' : 'var(--accent)'}; font-size: 13px; padding: 8px 16px;" onclick="setDictSubTab('${t}')">
      ${t}
    </button>
  `).join('');

  const profilesEnabled = state.settings.profiles_enabled !== false;

  let toggleHtml = `
    <div class="card flex-between" style="padding: 16px 24px; margin-bottom: 24px;">
      <div>
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">Enable Dictionary Customizations</div>
        <div style="font-size: 12px; color: var(--text-muted);">Apply vocabulary substitutions and text templates during dictation.</div>
      </div>
      <label class="toggle-switch">
        <input type="checkbox" ${profilesEnabled ? 'checked' : ''} onchange="updateSettingAndRender('profiles_enabled', this.checked)">
        <span class="slider"></span>
      </label>
    </div>
  `;

  let headerHtml = `
    <div class="card" style="display: flex; gap: 24px; align-items: flex-end; margin-bottom: 24px; padding: 18px 24px;">
      <div style="flex: 1.2; max-width: 400px;">
        <label class="label">Active Dictionary</label>
        <div style="display: flex; gap: 8px;">
          <select class="input-field" style="padding: 10px 14px; flex: 1;" onchange="onActiveDictionaryChange(this.value)">
            ${dictOptions}
          </select>
          <button class="btn" style="padding: 0 16px; font-size: 20px; line-height: 1; display: flex; align-items: center; justify-content: center;" onclick="addNewProfile()" title="Create New Dictionary">+</button>
        </div>
      </div>
      <div style="flex: 1; max-width: 300px;">
        <label class="label">Dictionary Keybind</label>
        <input class="input-field" type="text" value="${escapeHtml(currentBind)}" placeholder="e.g. ctrl+alt+p" readonly
               onkeydown="captureKey(event); updateDictionaryKeybind('${activeDict}', event.target.value);">
      </div>
    </div>
  `;

  let subContentHtml = '';
  
  if (state.dictSubTab === 'Vocabulary') {
    const subs = state.dictData.substitutions || {};
    
    const groupedSubs = {};
    for (const [trigger, repl] of Object.entries(subs)) {
      if (trigger.startsWith("_")) continue;
      // Filter out symbols and formatting commands
      if (window.isSymbolOrFormatting(trigger, repl)) continue;
      if (!groupedSubs[repl]) {
        groupedSubs[repl] = [];
      }
      groupedSubs[repl].push(trigger);
    }

    const sortedRepls = Object.keys(groupedSubs).sort();
    let subsRows = '';
    
    sortedRepls.forEach(repl => {
      const triggers = groupedSubs[repl];
      triggers.sort();
      const triggersStr = triggers.join(", ");
      const cleanRepl = escapeHtml(repl);
      const triggersJson = escapeHtml(JSON.stringify(triggers));
      
      subsRows += `
        <div class="dict-table-row">
          <div class="dict-col-spoken" contenteditable="true" 
               onblur="updateSubGroupTriggers('substitutions', this.getAttribute('data-triggers'), this.innerText)" 
               data-triggers="${triggersJson}"
               title="Click to edit triggers (comma-separated)" style="outline: none; cursor: text; font-family: monospace; font-size: 13px;">${triggersStr}</div>
          <div class="dict-col-repl" contenteditable="true" 
               onblur="updateSubGroupValue('substitutions', this.getAttribute('data-triggers'), this.innerText)" 
               data-triggers="${triggersJson}"
               title="Click to edit replacement" style="outline: none; cursor: text; white-space: pre-wrap; font-family: inherit;">${cleanRepl}</div>
          <div class="dict-col-actions">
            <button class="delete-action" onclick="deleteSubGroup('substitutions', this.getAttribute('data-triggers'))" data-triggers="${triggersJson}" title="Delete">×</button>
          </div>
        </div>
      `;
    });

    subContentHtml = `
      <div style="display: flex; flex-direction: column; opacity: ${profilesEnabled ? 1 : 0.5}; pointer-events: ${profilesEnabled ? 'auto' : 'none'};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 0 8px;">
          <h4 class="label" style="font-size:12px; margin: 0;">Vocabulary / Word Replacement</h4>
        </div>
        <div class="dict-table">
          <div class="dict-table-header">
            <div class="dict-header-spoken">Spoken Trigger</div>
            <div class="dict-header-repl">Word Replacement</div>
            <div class="dict-header-actions"></div>
          </div>
          <div style="max-height: 380px; overflow-y: auto;">
            ${subsRows || '<div style="padding: 16px; color: var(--text-muted); font-size: 13px;">No vocabulary replacements defined.</div>'}
          </div>
          <div class="inline-add-row">
            <input id="new_vocab_phrase" class="input-field" placeholder="Spoken variants (e.g. uplane, you plane)" style="flex:1;">
            <input id="new_vocab_repl" class="input-field" placeholder="Replacement (e.g. U.Plane)" style="flex:1.2;">
            <button class="btn-inline-add" onclick="addSubGroup('substitutions')">+ Add</button>
          </div>
        </div>
      </div>
    `;
  } else if (state.dictSubTab === 'Templates') {
    const macros = state.dictData.macros || {};
    
    const groupedMacros = {};
    for (const [trigger, repl] of Object.entries(macros)) {
      if (trigger.startsWith("_")) continue;
      if (!groupedMacros[repl]) {
        groupedMacros[repl] = [];
      }
      groupedMacros[repl].push(trigger);
    }

    const sortedRepls = Object.keys(groupedMacros).sort();
    let macrosRows = '';
    
    sortedRepls.forEach(repl => {
      const triggers = groupedMacros[repl];
      triggers.sort();
      const triggersStr = triggers.join(", ");
      const cleanRepl = escapeHtml(repl);
      const triggersJson = escapeHtml(JSON.stringify(triggers));
      
      macrosRows += `
        <div class="dict-table-row">
          <div class="dict-col-spoken" contenteditable="true" 
               onblur="updateSubGroupTriggers('macros', this.getAttribute('data-triggers'), this.innerText)" 
               data-triggers="${triggersJson}"
               title="Click to edit triggers (comma-separated)" style="outline: none; cursor: text; font-family: monospace; font-size: 13px;">${triggersStr}</div>
          <div class="dict-col-repl" contenteditable="true" 
               onblur="updateSubGroupValue('macros', this.getAttribute('data-triggers'), this.innerText)" 
               data-triggers="${triggersJson}"
               title="Click to edit template content" style="outline: none; cursor: text; white-space: pre-wrap; font-family: monospace; font-size: 13px;">${cleanRepl}</div>
          <div class="dict-col-actions">
            <button class="delete-action" onclick="deleteSubGroup('macros', this.getAttribute('data-triggers'))" data-triggers="${triggersJson}" title="Delete">×</button>
          </div>
        </div>
      `;
    });

    subContentHtml = `
      <div style="display: flex; flex-direction: column; opacity: ${profilesEnabled ? 1 : 0.5}; pointer-events: ${profilesEnabled ? 'auto' : 'none'};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 0 8px;">
          <h4 class="label" style="font-size:12px; margin: 0;">Text Templates & Snippets</h4>
        </div>
        <div class="dict-table">
          <div class="dict-table-header">
            <div class="dict-header-spoken">Spoken Trigger</div>
            <div class="dict-header-repl">Text Template</div>
            <div class="dict-header-actions"></div>
          </div>
          <div style="max-height: 380px; overflow-y: auto;">
            ${macrosRows || '<div style="padding: 16px; color: var(--text-muted); font-size: 13px;">No templates defined.</div>'}
          </div>
          <div class="inline-add-row">
            <input id="new_temp_phrase" class="input-field" placeholder="Trigger phrases (e.g. email signature)" style="flex:1;">
            <textarea id="new_temp_repl" class="input-field" placeholder="Template text snippet (use Enter for line breaks)" style="flex:1.5; min-height: 60px; max-height: 200px; resize: vertical; font-family: monospace; font-size: 13px; padding: 8px 12px; white-space: pre-wrap;" rows="3"></textarea>
            <button class="btn-inline-add" onclick="addSubGroup('macros')">+ Add</button>
          </div>
        </div>
      </div>
    `;
  }

  let blacklistHtml = `
    <div class="card" style="margin-top: 24px; opacity: ${profilesEnabled ? 1 : 0.5}; pointer-events: ${profilesEnabled ? 'auto' : 'none'};">
      <div class="form-group">
        <label class="label">Vocabulary / Hallucination Blacklist</label>
        <input class="input-field" type="text" value="${escapeHtml(state.settings.vocabulary_blacklist || '')}" 
               placeholder="e.g. thanks for watching, please subscribe, bye bye"
               onchange="updateSettingAndRender('vocabulary_blacklist', this.value)">
        <p style="font-size: 12px; color: var(--text-muted); margin-top: 6px;">Comma-separated words or phrases to completely strip out of transcriptions (useful for blocking persistent Whisper hallucinations or mishears).</p>
      </div>
    </div>
  `;

  let html = `
    ${toggleHtml}
    ${headerHtml}
    <div style="margin-bottom: 24px; display: flex; align-items: center; opacity: ${profilesEnabled ? 1 : 0.5}; pointer-events: ${profilesEnabled ? 'auto' : 'none'};">
      ${subTabsHtml}
    </div>
    ${subContentHtml}
    ${blacklistHtml}
  `;

  return html;
}

function renderDictationCommandsTab() {
  const commands = state.dictData.voice_commands || {};
  const inDictationCommandsEnabled = state.settings.in_dictation_commands_enabled !== false;

  let toggleHtml = `
    <div class="card flex-between" style="padding: 16px 24px; margin-bottom: 24px;">
      <div>
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">Enable Voice Commands</div>
        <div style="font-size: 12px; color: var(--text-muted);">Process in-dictation formatting commands and post-paste commit actions.</div>
      </div>
      <label class="toggle-switch">
        <input type="checkbox" ${inDictationCommandsEnabled ? 'checked' : ''} onchange="updateSettingAndRender('in_dictation_commands_enabled', this.checked)">
        <span class="slider"></span>
      </label>
    </div>
  `;

  const duringLabels = {
    'caps_on': 'ALL CAPS',
    'caps_off': 'lowercase',
    'cap_next': 'Capitalize Next Word',
    'bold_on': 'Bold On',
    'bold_off': 'Bold Off',
    'italic_on': 'Italic On',
    'italic_off': 'Italic Off',
    'code_on': 'Code On',
    'code_off': 'Code Off',
    'strikethrough_on': 'Strikethrough On',
    'strikethrough_off': 'Strikethrough Off',
    'code_block_on': 'Code Block On',
    'code_block_off': 'Code Block Off',
    'blockquote_on': 'Blockquote On',
    'blockquote_off': 'Blockquote Off',
    'bullet_list_on': 'Bullet List On',
    'bullet_list_off': 'Bullet List Off',
    'numbered_list_on': 'Numbered List On',
    'numbered_list_off': 'Numbered List Off',
    'heading_h1': 'Heading 1',
    'heading_h2': 'Heading 2',
    'heading_h3': 'Heading 3',
    'indent_in': 'Indent In',
    'indent_out': 'Indent Out',
    'link': 'Insert Link',
    'new_line': 'New Line',
    'new_paragraph': 'New Paragraph'
  };

  const afterLabels = {
    'submit': 'Send / Enter (Ctrl+Enter)',
    'select_all': 'Select All (Ctrl+A)',
    'delete_all': 'Delete All (Ctrl+A, Backspace)'
  };

  let duringRows = '';
  let afterRows = '';

  const sortedTriggers = Object.keys(commands).sort();

  sortedTriggers.forEach(phrase => {
    if (phrase.startsWith("_")) return;
    const cmd = commands[phrase];
    const isAfter = cmd.phase === 'after';

    let typeLabel = 'Unknown';
    if (cmd.action === 'submit') {
      typeLabel = afterLabels['submit'];
    } else if (cmd.action === 'key') {
      if (cmd.keys && cmd.keys.includes('backspace')) {
        typeLabel = afterLabels['delete_all'];
      } else {
        typeLabel = afterLabels['select_all'];
      }
    } else if (cmd.action === 'transform') {
      typeLabel = duringLabels[cmd.type] || cmd.type || 'Unknown';
    }

    const rowHtml = `
      <div class="dict-table-row">
        <div style="flex: 1.2; font-weight: 600;">"${phrase}"</div>
        <div style="flex: 2; font-size: 13px; color: var(--accent); font-family: monospace;">Action: ${typeLabel}</div>
        <div class="dict-col-actions">
          <button class="delete-action" onclick="deleteVoiceCommandItem('${phrase}')" title="Delete">×</button>
        </div>
      </div>
    `;

    if (isAfter) {
      afterRows += rowHtml;
    } else {
      duringRows += rowHtml;
    }
  });

  // Symbols & Typing Shortcuts
  const subs = state.dictData.substitutions || {};
  const groupedSymbols = {};
  for (const [trigger, repl] of Object.entries(subs)) {
    if (trigger.startsWith("_")) continue;
    if (!window.isSymbolOrFormatting(trigger, repl)) continue;
    if (!groupedSymbols[repl]) {
      groupedSymbols[repl] = [];
    }
    groupedSymbols[repl].push(trigger);
  }
  const sortedSymbolRepls = Object.keys(groupedSymbols).sort();
  let symbolsRows = '';
  sortedSymbolRepls.forEach(repl => {
    const triggers = groupedSymbols[repl];
    triggers.sort();
    const triggersStr = triggers.join(", ");
    const cleanRepl = escapeHtml(repl);
    const triggersJson = escapeHtml(JSON.stringify(triggers));
    
    symbolsRows += `
      <div class="dict-table-row">
        <div class="dict-col-spoken" contenteditable="true" 
             onblur="updateSubGroupTriggers('substitutions', this.getAttribute('data-triggers'), this.innerText)" 
             data-triggers="${triggersJson}"
             title="Click to edit triggers (comma-separated)" style="outline: none; cursor: text; font-family: monospace; font-size: 13px;">${triggersStr}</div>
        <div class="dict-col-repl" contenteditable="true" 
             onblur="updateSubGroupValue('substitutions', this.getAttribute('data-triggers'), this.innerText)" 
             data-triggers="${triggersJson}"
             title="Click to edit symbol" style="outline: none; cursor: text; white-space: pre-wrap; font-family: inherit;">${cleanRepl}</div>
        <div class="dict-col-actions">
          <button class="delete-action" onclick="deleteSubGroup('substitutions', this.getAttribute('data-triggers'))" data-triggers="${triggersJson}" title="Delete">×</button>
        </div>
      </div>
    `;
  });
  const displayStyle = inDictationCommandsEnabled ? '' : 'opacity: 0.5; pointer-events: none;';

  return `
    ${toggleHtml}
    
    <div style="display: flex; flex-direction: column; gap: 16px; ${displayStyle}">
      <!-- Section 1: During Dictation -->
      <div class="card" style="margin-bottom: 0; cursor: pointer; padding: 20px 24px;" onclick="toggleSection('during')">
        <div class="flex-between">
          <div>
            <h3 style="font-size: 14.5px; font-weight: 600; margin: 0; color: #fff; text-align: left;">Formatting & Casing Controls</h3>
            <span style="font-size: 12px; color: var(--text-muted); display: block; margin-top: 4px; text-align: left;">Configure casing, bold, italic, and code formatting commands.</span>
          </div>
          <svg style="width: 18px; height: 18px; color: var(--text-muted); transition: transform 0.2s; transform: ${state.expandedSections.during ? 'rotate(180deg)' : 'rotate(0deg)'}" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        ${state.expandedSections.during ? `
          <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-light); cursor: default;" onclick="event.stopPropagation()">
            <div class="dict-table" style="margin-bottom: 0;">
              <div class="dict-table-header">
                <div class="dict-header-spoken" style="flex: 1.2;">Spoken Trigger</div>
                <div class="dict-header-repl" style="flex: 2;">Action / Transform</div>
                <div class="dict-header-actions"></div>
              </div>
              <div style="max-height: 200px; overflow-y: auto;">
                ${duringRows || '<div style="padding: 16px; color: var(--text-muted); font-size: 13px;">No formatting controls defined.</div>'}
              </div>
              <div class="inline-add-row" style="gap: 12px;">
                <input id="new_vc_during_trigger" class="input-field" style="flex: 1.2;" placeholder="Spoken trigger (e.g. bold that)">
                <select id="new_vc_during_type" class="input-field" style="flex: 1.5; padding: 8px 12px;">
                  <option value="caps_on">ALL CAPS</option>
                  <option value="caps_off">lowercase</option>
                  <option value="cap_next">Capitalize Next Word</option>
                  <option value="bold_on">Bold On</option>
                  <option value="bold_off">Bold Off</option>
                  <option value="italic_on">Italic On</option>
                  <option value="italic_off">Italic Off</option>
                  <option value="code_on">Code On</option>
                  <option value="code_off">Code Off</option>
                  <option value="strikethrough_on">Strikethrough On</option>
                  <option value="strikethrough_off">Strikethrough Off</option>
                  <option value="code_block_on">Code Block On</option>
                  <option value="code_block_off">Code Block Off</option>
                  <option value="blockquote_on">Blockquote On</option>
                  <option value="blockquote_off">Blockquote Off</option>
                  <option value="bullet_list_on">Bullet List On</option>
                  <option value="bullet_list_off">Bullet List Off</option>
                  <option value="numbered_list_on">Numbered List On</option>
                  <option value="numbered_list_off">Numbered List Off</option>
                  <option value="heading_h1">Heading 1</option>
                  <option value="heading_h2">Heading 2</option>
                  <option value="heading_h3">Heading 3</option>
                  <option value="indent_in">Indent In</option>
                  <option value="indent_out">Indent Out</option>
                  <option value="link">Insert Link</option>
                  <option value="new_line">New Line</option>
                  <option value="new_paragraph">New Paragraph</option>
                </select>
                <button class="btn-inline-add" onclick="addVoiceCommandItem('during')">+ Add Control</button>
              </div>
            </div>
          </div>
        ` : ''}
      </div>

      <!-- Section 2: After Pasting -->
      <div class="card" style="margin-bottom: 0; cursor: pointer; padding: 20px 24px;" onclick="toggleSection('after')">
        <div class="flex-between">
          <div>
            <h3 style="font-size: 14.5px; font-weight: 600; margin: 0; color: #fff; text-align: left;">Commit & Action Commands</h3>
            <span style="font-size: 12px; color: var(--text-muted); display: block; margin-top: 4px; text-align: left;">Configure actions like Select All or Enter to trigger after text is pasted.</span>
          </div>
          <svg style="width: 18px; height: 18px; color: var(--text-muted); transition: transform 0.2s; transform: ${state.expandedSections.after ? 'rotate(180deg)' : 'rotate(0deg)'}" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        ${state.expandedSections.after ? `
          <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-light); cursor: default;" onclick="event.stopPropagation()">
            <div class="dict-table" style="margin-bottom: 0;">
              <div class="dict-table-header">
                <div class="dict-header-spoken" style="flex: 1.2;">Spoken Trigger</div>
                <div class="dict-header-repl" style="flex: 2;">Action / Transform</div>
                <div class="dict-header-actions"></div>
              </div>
              <div style="max-height: 200px; overflow-y: auto;">
                ${afterRows || '<div style="padding: 16px; color: var(--text-muted); font-size: 13px;">No commit actions defined.</div>'}
              </div>
              <div class="inline-add-row" style="gap: 12px;">
                <input id="new_vc_after_trigger" class="input-field" style="flex: 1.2;" placeholder="Spoken trigger (e.g. send message)">
                <select id="new_vc_after_type" class="input-field" style="flex: 1.5; padding: 8px 12px;">
                  <option value="submit">Send / Enter (Ctrl+Enter)</option>
                  <option value="select_all">Select All (Ctrl+A)</option>
                  <option value="delete_all">Delete All (Ctrl+A, Backspace)</option>
                </select>
                <button class="btn-inline-add" onclick="addVoiceCommandItem('after')">+ Add Action</button>
              </div>
            </div>
          </div>
        ` : ''}
      </div>

      <!-- Section 3: Symbols & Typing Shortcuts -->
      <div class="card" style="margin-bottom: 0; cursor: pointer; padding: 20px 24px;" onclick="toggleSection('symbols')">
        <div class="flex-between">
          <div>
            <h3 style="font-size: 14.5px; font-weight: 600; margin: 0; color: #fff; text-align: left;">Symbols & Typing Shortcuts</h3>
            <span style="font-size: 12px; color: var(--text-muted); display: block; margin-top: 4px; text-align: left;">Define spoken words that expand into symbols, punctuation, or paragraph breaks.</span>
          </div>
          <svg style="width: 18px; height: 18px; color: var(--text-muted); transition: transform 0.2s; transform: ${state.expandedSections.symbols ? 'rotate(180deg)' : 'rotate(0deg)'}" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        ${state.expandedSections.symbols ? `
          <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-light); cursor: default;" onclick="event.stopPropagation()">
            <div class="dict-table" style="margin-bottom: 0;">
              <div class="dict-table-header">
                <div class="dict-header-spoken">Spoken Trigger</div>
                <div class="dict-header-repl">Character / Formatting</div>
                <div class="dict-header-actions"></div>
              </div>
              <div style="max-height: 200px; overflow-y: auto;">
                ${symbolsRows || '<div style="padding: 16px; color: var(--text-muted); font-size: 13px;">No symbols defined.</div>'}
              </div>
              <div class="inline-add-row">
                <input id="new_symbol_phrase" class="input-field" placeholder="Spoken trigger (e.g. equals sign)" style="flex:1;">
                <input id="new_symbol_repl" class="input-field" placeholder="Symbol / character (e.g. =)" style="flex:1.2;">
                <button class="btn-inline-add" onclick="addSubGroup('symbols')">+ Add Symbol</button>
              </div>
            </div>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

// Wake Words
window.deleteWakeWord = function(index) {
  state.settings.wake_words.splice(index, 1);
  render();
};

window.updateWakeWordValue = function(index, key, val) {
  state.settings.wake_words[index][key] = val;
  if(key !== 'threshold') render(); // don't re-render while dragging slider
};

window.startWakeWordWizard = function() {
  state.confirmWizardModal = { type: 'train' };
  render();
};

window.startWakeWordPersonalize = function(phrase, modelName) {
  state.confirmWizardModal = { type: 'personalize', phrase: phrase, modelName: modelName };
  render();
};

function renderWakeWordsTab() {
  const words = state.settings.wake_words || [];
  const wakeWordsEnabled = state.settings.wake_words_enabled !== false;

  let toggleHtml = `
    <div class="card flex-between" style="padding: 16px 24px; margin-bottom: 24px;">
      <div>
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">Enable Wake Words</div>
        <div style="font-size: 12px; color: var(--text-muted);">Listen continuously in the background for voice wake words (like "cv_go").</div>
      </div>
      <label class="toggle-switch">
        <input type="checkbox" ${wakeWordsEnabled ? 'checked' : ''} onchange="updateSettingAndRender('wake_words_enabled', this.checked)">
        <span class="slider"></span>
      </label>
    </div>
  `;

  let wizardCardHtml = `
    <div class="card" style="border: 1px solid var(--accent); background: rgba(59, 130, 246, 0.05); margin-top: 32px; opacity: ${wakeWordsEnabled ? 1 : 0.5}; pointer-events: ${wakeWordsEnabled ? 'auto' : 'none'};">
      <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px;">
        <div>
          <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">Train Custom Wake Word</div>
          <div style="font-size: 12px; color: var(--text-muted);">Launch a step-by-step terminal wizard to train a new ONNX model on your voice.</div>
        </div>
        <button class="btn" onclick="startWakeWordWizard()">Train New Word</button>
      </div>
    </div>
  `;

  let listHtml = '';
  words.forEach((w, i) => {
    listHtml += `
      <div class="card" style="margin-bottom: 16px; opacity: ${wakeWordsEnabled ? 1 : 0.5}; pointer-events: ${wakeWordsEnabled ? 'auto' : 'none'};">
        <div style="display: flex; gap: 24px; align-items: stretch;">
          <div style="flex: 2.2; display: flex; flex-direction: column; gap: 12px;">
            <div>
              <label class="label">Name</label>
              <input class="input-field" value="${w.name}" onchange="updateWakeWordValue(${i}, 'name', this.value)">
            </div>
            <details style="margin-top: 10px;">
              <summary style="font-size: 12px; color: var(--text-muted); cursor: pointer; user-select: none; outline: none;">Advanced: Model Path</summary>
              <div style="margin-top: 8px;">
                <label class="label" style="font-size: 11px;">Model File Path</label>
                <input class="input-field" value="${w.model_path || w.path || ''}" onchange="updateWakeWordValue(${i}, 'model_path', this.value)">
              </div>
            </details>
          </div>
          <div style="flex: 1.8; display: flex; flex-direction: column; gap: 12px;">
            <div>
              <label class="label">Role</label>
              <select class="input-field" onchange="updateWakeWordValue(${i}, 'role', this.value)">
                <option value="start" ${w.role==='start'?'selected':''}>start</option>
                <option value="stop" ${w.role==='stop'?'selected':''}>stop</option>
              </select>
            </div>
            <div>
              <label class="label">Sensitivity</label>
              <div style="display: flex; gap: 8px; align-items: center;">
                <input type="range" class="range-slider" min="0" max="1" step="any" value="${w.threshold}"
                       oninput="updateWakeWordValue(${i}, 'threshold', parseFloat(this.value)); this.nextElementSibling.value=Number(this.value).toFixed(2);" style="flex: 1;">
                <input type="number" class="input-field" style="width: 90px;" min="0" max="1" step="0.01" value="${Number(w.threshold).toFixed(2)}"
                       onchange="updateWakeWordValue(${i}, 'threshold', parseFloat(this.value)); this.previousElementSibling.value=this.value;">
              </div>
            </div>
          </div>
          <div style="display: flex; align-items: center; justify-content: center; padding-left: 8px;">
            <button class="delete-wake-btn" onclick="deleteWakeWord(${i})" title="Delete Wake Word">🗑</button>
          </div>
        </div>
      </div>
    `;
  });

  let enhanceCardHtml = '';
  if (words.length > 0) {
    let enhanceButtonsHtml = '';
    words.forEach((w) => {
      const phraseGuess = w.name.replace(/[_-]/g, ' ').trim();
      enhanceButtonsHtml += `
        <button class="btn btn-secondary" style="margin-right: 8px; margin-bottom: 8px;" onclick="startWakeWordPersonalize('${phraseGuess}', '${w.name}')">
          Personalize "${w.name}"
        </button>
      `;
    });

    enhanceCardHtml = `
      <div class="card" style="margin-top: 24px; opacity: ${wakeWordsEnabled ? 1 : 0.5}; pointer-events: ${wakeWordsEnabled ? 'auto' : 'none'};">
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">Personalize for Your Voice</div>
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
          Tune an active wake word (like <code>cv_go</code> or <code>cv_over</code>) to your specific voice. Records you saying the wake word 5 times plus 10 seconds of normal speech, then calibrates the trigger threshold to your audio. About 60 seconds, no downloads.
        </div>
        <div style="display: flex; flex-wrap: wrap;">
          ${enhanceButtonsHtml}
        </div>
      </div>
    `;
  }

  return `
    ${toggleHtml}
    ${listHtml}
    ${enhanceCardHtml}
    ${wizardCardHtml}
  `;
}

function renderPresenceTab() {
  const s = state.settings;
  const showGlowBar = s.show_glow_bar !== false;
  const glowBarPosition = s.glow_bar_position || 'top';
  const glowBarHeight = s.glow_bar_height !== undefined ? s.glow_bar_height : 60;
  const glowBarBrightness = s.glow_bar_brightness !== undefined ? s.glow_bar_brightness : 0.75;
  const glowBarX = s.glow_bar_x !== undefined ? s.glow_bar_x : 0;
  const glowBarY = s.glow_bar_y !== undefined ? s.glow_bar_y : 0;

  const showStartStopButton = s.show_start_stop_button === true;
  const startStopButtonLocked = s.start_stop_button_locked === true;
  const startStopButtonSize = s.start_stop_button_size !== undefined ? s.start_stop_button_size : 160;
  const startStopButtonX = s.start_stop_button_x !== undefined ? s.start_stop_button_x : -1;
  const startStopButtonY = s.start_stop_button_y !== undefined ? s.start_stop_button_y : -1;
  const showTrayIcon = s.show_tray_icon !== false;

  const isFreeform = glowBarPosition === 'freeform';

  return `
    <!-- Glow Bar Settings -->
    <div class="card">
      <div class="flex-between" style="margin-bottom: 24px;">
        <div>
          <div style="font-weight: 600; font-size: 14.5px; margin-bottom: 4px; text-align: left;">Enable Glow Bar</div>
          <div style="font-size: 12px; color: var(--text-muted); text-align: left;">Show a colored ambient edge glow representing dictation state.</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" ${showGlowBar ? 'checked' : ''} onchange="updateSettingAndRender('show_glow_bar', this.checked)">
          <span class="slider"></span>
        </label>
      </div>

      <div style="opacity: ${showGlowBar ? 1 : 0.5}; pointer-events: ${showGlowBar ? 'auto' : 'none'}; display: flex; flex-direction: column; gap: 20px;">
        <div class="form-group" style="margin: 0;">
          <label class="label">Glow Bar Position</label>
          <select class="input-field" onchange="updateSettingAndRender('glow_bar_position', this.value)">
            <option value="top" ${glowBarPosition === 'top' ? 'selected' : ''}>Top Edge</option>
            <option value="bottom" ${glowBarPosition === 'bottom' ? 'selected' : ''}>Bottom Edge</option>
            <option value="left" ${glowBarPosition === 'left' ? 'selected' : ''}>Left Edge</option>
            <option value="right" ${glowBarPosition === 'right' ? 'selected' : ''}>Right Edge</option>
            <option value="freeform" ${glowBarPosition === 'freeform' ? 'selected' : ''}>Freeform (Custom Position)</option>
          </select>
        </div>

        <div class="form-group" style="margin: 0;">
          <label class="label">Glow Bar Height</label>
          <div style="display: flex; gap: 16px; align-items: center;">
            <input type="range" class="range-slider" min="20" max="150" value="${glowBarHeight}"
                   oninput="updateSetting('glow_bar_height', parseInt(this.value)); this.nextElementSibling.value=this.value" style="flex:1;">
            <input type="number" class="input-field" style="width: 80px;" min="20" max="150" value="${glowBarHeight}"
                   onchange="updateSetting('glow_bar_height', parseInt(this.value)); this.previousElementSibling.value=this.value">
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-top: 6px; text-align: left;">Thickness of the glow bar in pixels (recommended: 60px for soft falloff).</p>
        </div>

        <div class="form-group" style="margin: 0;">
          <label class="label">Glow Bar Brightness</label>
          <div style="display: flex; gap: 16px; align-items: center;">
            <input type="range" class="range-slider" min="0" max="1" step="0.05" value="${glowBarBrightness}"
                   oninput="updateSetting('glow_bar_brightness', parseFloat(this.value)); this.nextElementSibling.value=Math.round(this.value * 100) + '%'" style="flex:1;">
            <input type="text" class="input-field" style="width: 80px; text-align: center;" readonly value="${Math.round(glowBarBrightness * 100)}%">
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-top: 6px; text-align: left;">Peak brightness (opacity multiplier) for colors.</p>
        </div>

        ${isFreeform ? `
          <div class="grid-2">
            <div class="form-group" style="margin: 0;">
              <label class="label">Freeform X Coordinate</label>
              <input type="number" class="input-field" value="${glowBarX}" onchange="updateSetting('glow_bar_x', parseInt(this.value))">
            </div>
            <div class="form-group" style="margin: 0;">
              <label class="label">Freeform Y Coordinate</label>
              <input type="number" class="input-field" value="${glowBarY}" onchange="updateSetting('glow_bar_y', parseInt(this.value))">
            </div>
          </div>
        ` : ''}
      </div>
    </div>

    <!-- Floating Button & Tray Settings -->
    <div class="card">
      <div class="flex-between" style="margin-bottom: 24px;">
        <div>
          <div style="font-weight: 600; font-size: 14.5px; margin-bottom: 4px; text-align: left;">Enable Floating Start/Stop Button</div>
          <div style="font-size: 12px; color: var(--text-muted); text-align: left;">Show a draggable circular overlay button to toggle dictation.</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" ${showStartStopButton ? 'checked' : ''} onchange="updateSettingAndRender('show_start_stop_button', this.checked)">
          <span class="slider"></span>
        </label>
      </div>

      <div style="opacity: ${showStartStopButton ? 1 : 0.5}; pointer-events: ${showStartStopButton ? 'auto' : 'none'}; display: flex; flex-direction: column; gap: 20px;">
        <div class="flex-between" style="margin-bottom: 8px;">
          <div>
            <div style="font-weight: 600; font-size: 14.5px; margin-bottom: 4px; text-align: left;">Lock Button Position</div>
            <div style="font-size: 12px; color: var(--text-muted); text-align: left;">Prevent dragging the button with the mouse.</div>
          </div>
          <label class="toggle-switch">
            <input type="checkbox" ${startStopButtonLocked ? 'checked' : ''} onchange="updateSettingAndRender('start_stop_button_locked', this.checked)">
            <span class="slider"></span>
          </label>
        </div>

        <div class="form-group" style="margin: 0;">
          <label class="label">Button Size</label>
          <div style="display: flex; gap: 16px; align-items: center;">
            <input type="range" class="range-slider" min="40" max="300" value="${startStopButtonSize}"
                   oninput="updateSetting('start_stop_button_size', parseInt(this.value)); this.nextElementSibling.value=this.value" style="flex:1;">
            <input type="number" class="input-field" style="width: 80px;" min="40" max="300" value="${startStopButtonSize}"
                   onchange="updateSetting('start_stop_button_size', parseInt(this.value)); this.previousElementSibling.value=this.value">
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-top: 6px; text-align: left;">Diameter of the button in pixels (default: 160px; smaller than 72px uses fallback state glyphs).</p>
        </div>

        <div class="grid-2">
          <div class="form-group" style="margin: 0;">
            <label class="label">Button X Coordinate</label>
            <input type="number" class="input-field" value="${startStopButtonX}" onchange="updateSetting('start_stop_button_x', parseInt(this.value))">
            <span style="font-size: 11px; color: var(--text-muted); display: block; margin-top: 4px; text-align: left;">Use -1 for bottom-right snap.</span>
          </div>
          <div class="form-group" style="margin: 0;">
            <label class="label">Button Y Coordinate</label>
            <input type="number" class="input-field" value="${startStopButtonY}" onchange="updateSetting('start_stop_button_y', parseInt(this.value))">
            <span style="font-size: 11px; color: var(--text-muted); display: block; margin-top: 4px; text-align: left;">Use -1 for bottom-right snap.</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Tray Settings -->
    <div class="card">
      <div class="flex-between">
        <div>
          <div style="font-weight: 600; font-size: 14.5px; margin-bottom: 4px; text-align: left;">Show System Tray Icon</div>
          <div style="font-size: 12px; color: var(--text-muted); text-align: left;">Keep an icon in the Windows taskbar notifications area for easy menu access.</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" ${showTrayIcon ? 'checked' : ''} onchange="updateSettingAndRender('show_tray_icon', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
    </div>
  `;
}

// Dictation Log Tab
window.refreshDictationLog = function() {
  if (state.backend) {
    state.backend.fetch_dictation_log((log_json) => {
      state.dictationLog = JSON.parse(log_json);
      render();
    });
  }
};

window.openLogFile = function() {
  if (state.backend) {
    state.backend.open_dictation_log_directory();
  }
};

window.copyTranscript = function(text) {
  if (state.backend) {
    state.backend.copy_to_clipboard(text);
  }
};

function formatTimestamp(isoStr) {
  try {
    const d = new Date(isoStr);
    return d.toLocaleString();
  } catch (e) {
    return isoStr;
  }
}

function renderDictationLogTab() {
  let html = `
    <div class="card" style="margin-bottom: 24px;">
      <span style="font-size: 14px; color: var(--text-muted);">Displays the most recent 100 dictations. Transcripts copy to clipboard.</span>
    </div>
  `;

  if (state.dictationLog.length === 0) {
    html += `
      <div style="text-align: center; padding: 48px; color: var(--text-muted); font-size: 14px;">
        No log entries found.
      </div>
    `;
    return html;
  }

  state.dictationLog.forEach(e => {
    html += `
      <div class="card" style="margin-bottom: 12px; padding: 18px 24px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
          <span style="font-size: 12px; color: var(--text-muted); font-family: monospace;">
            ${formatTimestamp(e.ts)} [${(e.lang || 'auto').toUpperCase()}]
          </span>
          <button class="btn" style="padding: 4px 12px; font-size: 12px;" onclick="copyTranscript(this.getAttribute('data-text'))" data-text="${escapeHtml(e.text)}">Copy</button>
        </div>
        <div style="font-size: 14px; line-height: 1.5; color: #fff; white-space: pre-wrap; font-family: sans-serif;">
          ${escapeHtml(e.text)}
        </div>
      </div>
    `;
  });

  return html;
}

function saveSettings() {
  if (state.backend) {
    state.backend.save_settings(JSON.stringify(state.settings));
    if (state.dictData) {
      state.backend.save_dictionary(state.settings.active_dictionary || 'Default', JSON.stringify(state.dictData, null, 4));
    }
    
    let oldToast = document.getElementById('save-toast');
    if (oldToast) oldToast.remove();
    
    const toast = document.createElement('div');
    toast.id = 'save-toast';
    toast.style.cssText = `
      position: absolute; top: 0px; right: 0px; 
      background: var(--primary); color: #fff; 
      padding: 10px 20px; border-radius: 6px;
      font-weight: 500; font-size: 14px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5);
      z-index: 1000; animation: fadeInOut 2.5s forwards;
      pointer-events: none;
    `;
    toast.innerText = "Settings Saved Successfully";
    document.querySelector('.content-area').appendChild(toast);
    setTimeout(() => { if (toast.parentNode) toast.remove(); }, 2500);
  }
}
window.saveSettings = saveSettings;

// ─── Engine Console ────────────────────────────────────────────────

function _colorizeLogLine(text) {
  // Color-code by log prefix
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  
  // Match [Tag] prefix patterns
  const prefixMatch = escaped.match(/^(\[[\w.]+\])/);
  if (prefixMatch) {
    const tag = prefixMatch[1];
    let color = '#8b949e'; // default gray
    if (tag.includes('Dictation')) color = '#58a6ff';      // blue
    else if (tag.includes('Wake') || tag.includes('wake')) color = '#d29922'; // amber
    else if (tag.includes('Bridge')) color = '#a5d6ff';     // light blue
    else if (tag.includes('App')) color = '#7ee787';        // green
    else if (tag.includes('Filter')) color = '#f0883e';     // orange
    else if (tag.includes('Error') || tag.includes('error') || tag.includes('Failed')) color = '#f85149'; // red
    else if (tag.includes('Settings') || tag.includes('Config')) color = '#bc8cff'; // purple
    return `<span style="color:${color}">${tag}</span>${escaped.slice(tag.length)}`;
  }
  
  // Highlight lines with "error", "failed", "warning" 
  if (/error|failed|exception/i.test(escaped)) {
    return `<span style="color:#f85149">${escaped}</span>`;
  }
  // Highlight separator lines
  if (/^={3,}/.test(escaped)) {
    return `<span style="color:#484f58">${escaped}</span>`;
  }
  return escaped;
}

function _formatTimestamp(ts) {
  const d = new Date(ts * 1000);
  const h = d.getHours().toString().padStart(2, '0');
  const m = d.getMinutes().toString().padStart(2, '0');
  const s = d.getSeconds().toString().padStart(2, '0');
  const ms = d.getMilliseconds().toString().padStart(3, '0');
  return `${h}:${m}:${s}.${ms}`;
}

function renderEngineConsoleTab() {
  const lines = state.engineLog.map(line => {
    const ts = `<span style="color:#484f58">${_formatTimestamp(line.timestamp)}</span>`;
    const text = _colorizeLogLine(line.text);
    return `<div style="line-height: 1.6; white-space: pre-wrap; word-break: break-all;">${ts}  ${text}</div>`;
  }).join('');

  return `
    <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 12px;">
      <div style="width: 8px; height: 8px; border-radius: 50%; background: ${state.engineLogPollTimer ? '#7ee787' : '#484f58'}; box-shadow: ${state.engineLogPollTimer ? '0 0 8px #7ee787' : 'none'};"></div>
      <span style="color: var(--text-muted); font-size: 13px;">
        ${state.engineLogPollTimer ? 'Live — polling every 500ms' : 'Disconnected'}
        · ${state.engineLog.length} lines captured
      </span>
    </div>
    <div id="engine-console-output" style="
      background: #0d1117;
      border: 1px solid #21262d;
      border-radius: 8px;
      padding: 16px;
      font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 12px;
      color: #c9d1d9;
      overflow-y: auto;
      max-height: calc(100vh - 300px);
      min-height: 400px;
    ">
      ${lines || '<span style="color:#484f58">Waiting for engine output...</span>'}
    </div>
  `;
}

function startEngineLogPolling() {
  if (state.engineLogPollTimer) return;
  state.engineLogPollTimer = setInterval(() => {
    if (!state.backend || state.activeTab !== 'Engine Console') {
      stopEngineLogPolling();
      return;
    }
    state.backend.fetch_engine_log(state.engineLogLastIndex, (json_str) => {
      const newLines = JSON.parse(json_str);
      if (newLines.length > 0) {
        state.engineLog.push(...newLines);
        state.engineLogLastIndex = newLines[newLines.length - 1].index;
        // Keep max 2000 lines in UI
        if (state.engineLog.length > 2000) {
          state.engineLog = state.engineLog.slice(-2000);
        }
        // Append to DOM directly (avoid full re-render flicker)
        const container = document.getElementById('engine-console-output');
        if (container) {
          const fragment = document.createDocumentFragment();
          for (const line of newLines) {
            const div = document.createElement('div');
            div.style.cssText = 'line-height: 1.6; white-space: pre-wrap; word-break: break-all;';
            const ts = `<span style="color:#484f58">${_formatTimestamp(line.timestamp)}</span>`;
            div.innerHTML = `${ts}  ${_colorizeLogLine(line.text)}`;
            fragment.appendChild(div);
          }
          // Remove the "Waiting..." placeholder if present
          const placeholder = container.querySelector('span');
          if (placeholder && placeholder.textContent.includes('Waiting')) {
            placeholder.remove();
          }
          container.appendChild(fragment);
          if (state.engineLogAutoScroll) {
            container.scrollTop = container.scrollHeight;
          }
        }
        // Update the status line
        const statusLine = document.querySelector('.content-scroll-pane > div:first-child + div span');
      }
    });
  }, 500);
}

function stopEngineLogPolling() {
  if (state.engineLogPollTimer) {
    clearInterval(state.engineLogPollTimer);
    state.engineLogPollTimer = null;
  }
}

window.clearEngineLog = function() {
  state.engineLog = [];
  render();
};

window.toggleEngineAutoScroll = function() {
  state.engineLogAutoScroll = !state.engineLogAutoScroll;
  render();
  if (state.engineLogAutoScroll) {
    const container = document.getElementById('engine-console-output');
    if (container) container.scrollTop = container.scrollHeight;
  }
};

function render() {
  if (!state.settings) {
    document.body.innerHTML = '<div style="padding: 20px; display: flex; align-items: center; justify-content: center; height: 100vh; color: var(--text-muted);">Loading configuration...</div>';
    return;
  }

  // 1. Capture scroll position and active element focus/selection
  const scrollPane = document.querySelector('.content-scroll-pane');
  const scrollTop = scrollPane ? scrollPane.scrollTop : 0;

  const activeElement = document.activeElement;
  let activeElementSelector = null;
  let selectionStart = null;
  let selectionEnd = null;

  if (activeElement && activeElement !== document.body) {
    if (activeElement.id) {
      activeElementSelector = `#${activeElement.id}`;
    } else if (activeElement.name) {
      activeElementSelector = `[name="${activeElement.name}"]`;
    } else if (activeElement.tagName === 'INPUT' || activeElement.tagName === 'SELECT' || activeElement.tagName === 'TEXTAREA') {
      const onchange = activeElement.getAttribute('onchange');
      const oninput = activeElement.getAttribute('oninput');
      const placeholder = activeElement.getAttribute('placeholder');
      const type = activeElement.getAttribute('type');

      if (onchange) {
        activeElementSelector = `${activeElement.tagName}[onchange="${onchange.replace(/"/g, '\\"')}"]`;
      } else if (oninput) {
        activeElementSelector = `${activeElement.tagName}[oninput="${oninput.replace(/"/g, '\\"')}"]`;
      } else if (placeholder) {
        activeElementSelector = `${activeElement.tagName}[placeholder="${placeholder.replace(/"/g, '\\"')}"]`;
      } else if (type) {
        activeElementSelector = `${activeElement.tagName}[type="${type}"]`;
      } else {
        activeElementSelector = activeElement.tagName;
      }

      if (activeElement.tagName === 'INPUT' && (activeElement.type === 'text' || activeElement.type === 'number')) {
        try {
          selectionStart = activeElement.selectionStart;
          selectionEnd = activeElement.selectionEnd;
        } catch (e) {}
      }
    }
  }

  const tabs = ['General', 'Presence Overlay', 'Keybinds', 'Dictionaries', 'Voice Editing', 'Colors', 'Voice Activation', 'Dictation Log', 'Engine Console'];
  let contentHtml = '';
  if (state.activeTab === 'Dictionaries') contentHtml = renderDictionaryTab();
  else if (state.activeTab === 'Voice Editing') contentHtml = renderDictationCommandsTab();
  else if (state.activeTab === 'General') contentHtml = renderGeneralTab();
  else if (state.activeTab === 'Keybinds') contentHtml = renderKeybindsTab();
  else if (state.activeTab === 'Colors') contentHtml = renderColorsTab();
  else if (state.activeTab === 'Voice Activation') contentHtml = renderWakeWordsTab();
  else if (state.activeTab === 'Presence Overlay') contentHtml = renderPresenceTab();
  else if (state.activeTab === 'Dictation Log') contentHtml = renderDictationLogTab();
  else if (state.activeTab === 'Engine Console') contentHtml = renderEngineConsoleTab();

  const sidebarHtml = tabs.map(tab => `
    <div class="tab-item ${state.activeTab === tab ? 'active' : ''}" data-tab="${tab}">
      ${tab}
    </div>
  `).join('');

  const noSaveFooterTabs = ['Dictation Log', 'Engine Console'];
  let footerHtml;
  if (state.activeTab === 'Dictation Log') {
    footerHtml = `
      <div class="footer-bar" style="display: flex; gap: 16px; justify-content: flex-start;">
        <button class="btn" style="padding: 10px 32px; font-weight: 600; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);" onclick="refreshDictationLog()">Refresh Log</button>
        <button class="btn btn-secondary" style="padding: 10px 32px; font-weight: 600; background: transparent; border: 1px solid var(--accent); color: var(--accent);" onclick="openLogFile()">Open Log Folder</button>
      </div>
    `;
  } else if (state.activeTab === 'Engine Console') {
    footerHtml = `
      <div class="footer-bar" style="display: flex; gap: 16px; justify-content: flex-start;">
        <button class="btn" style="padding: 10px 32px; font-weight: 600; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);" onclick="clearEngineLog()">Clear</button>
        <button class="btn btn-secondary" style="padding: 10px 32px; font-weight: 600; background: transparent; border: 1px solid var(--accent); color: var(--accent);" onclick="toggleEngineAutoScroll()">${state.engineLogAutoScroll ? '⏸ Pause Scroll' : '▶ Resume Scroll'}</button>
      </div>
    `;
  } else {
    footerHtml = `
      <div class="footer-bar">
        <button class="btn" style="padding: 10px 32px; font-weight: 600; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);" onclick="saveSettings()">Save Changes</button>
      </div>
    `;
  }

  const pageTitle = state.activeTab === 'Dictionaries' ? 'Dictionary Profiles' : state.activeTab;

  document.body.innerHTML = `
    <style>
      @keyframes fadeInOut {
        0% { opacity: 0; transform: translateY(-10px); }
        15% { opacity: 1; transform: translateY(0); }
        80% { opacity: 1; transform: translateY(0); }
        100% { opacity: 0; transform: translateY(-10px); }
      }
    </style>
    <div id="app-wrapper" style="display: flex; width: 100%; height: 100%;">
      <div class="sidebar">
        <h1 style="font-size: 20px; font-weight: 600; color: #fff; margin-bottom: 32px; padding-left: 16px;">Clarity.V</h1>
        ${sidebarHtml}
      </div>
      <div class="content-area">
        <div class="content-scroll-pane" style="height: calc(100% - 70px); overflow-y: auto; padding: 48px 48px 24px 48px; display: flex; flex-direction: column; box-sizing: border-box;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; padding-bottom: 16px; border-bottom: 1px solid var(--border-light);">
            <h2 class="page-title" style="margin: 0; font-size: 24px; font-weight: 500;">${pageTitle}</h2>
          </div>
          <div>
            ${contentHtml}
          </div>
        </div>
        ${footerHtml}
      </div>
    </div>
  `;

  if (state.confirmWizardModal) {
    const modalType = state.confirmWizardModal.type;
    const phrase = state.confirmWizardModal.phrase;
    const modelName = state.confirmWizardModal.modelName;
    const isPersonalize = modalType === 'personalize';
    
    let modalHtml = `
      <div id="confirm-modal" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(9, 9, 11, 0.75); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 10000;">
        <div class="card" style="width: 500px; padding: 32px; border: 1px solid var(--accent); box-shadow: 0 8px 32px rgba(0,0,0,0.5); display: flex; flex-direction: column; gap: 20px; margin-bottom: 0;">
          <h3 style="margin: 0; font-size: 18px; font-weight: 600; color: #fff;">${isPersonalize ? 'Personalize Wake Word' : 'Confirm Wake Word Training'}</h3>
          <div style="font-size: 13px; line-height: 1.6; color: var(--text-muted);">
            ${isPersonalize ? `Tunes <strong>"${phrase}"</strong> (Model: ${modelName}) to your specific voice. You'll be asked to say the wake word 5 times and then talk normally for 10 seconds. The trigger threshold gets calibrated to your audio. <strong>About 60 seconds, no downloads.</strong>` : 'Training a custom wake word requires downloading approximately <strong>17.5 GB</strong> of training datasets (background noises and voice generator files) to set up your local environment.<br/><br/>This is a one-time download on this computer.'}
            <br/><br/>
            
            <br/><br/>
            This download will run inside a new terminal window. Do you want to continue?
          </div>
          <div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 8px;">
            <button class="btn-secondary" onclick="closeConfirmWizardModal()">Cancel</button>
            <button class="btn" onclick="proceedWithWizard()" style="padding: 10px 20px; font-size: 13px;">Proceed</button>
          </div>
        </div>
      </div>
    `;
    document.body.innerHTML += modalHtml;
  }

  // 2. Restore scroll position of .content-scroll-pane
  const newScrollPane = document.querySelector('.content-scroll-pane');
  if (newScrollPane) {
    newScrollPane.scrollTop = scrollTop;
  }

  // 3. Restore focus and selection
  if (activeElementSelector) {
    try {
      const newActive = document.querySelector(activeElementSelector);
      if (newActive) {
        newActive.focus();
        if (selectionStart !== null && selectionEnd !== null && (newActive.type === 'text' || newActive.type === 'number')) {
          newActive.setSelectionRange(selectionStart, selectionEnd);
        }
      }
    } catch (e) {
      console.warn("Could not restore focus:", e);
    }
  }

  document.querySelectorAll('.tab-item').forEach(el => {
    el.addEventListener('click', (e) => {
      const newTab = e.currentTarget.getAttribute('data-tab');
      // Stop engine log polling when leaving Engine Console tab
      if (state.activeTab === 'Engine Console' && newTab !== 'Engine Console') {
        stopEngineLogPolling();
      }
      state.activeTab = newTab;
      render();
      // Start engine log polling when entering Engine Console tab
      if (newTab === 'Engine Console') {
        startEngineLogPolling();
      }
    });
  });

  // Auto-start polling if we rendered on the Engine Console tab
  if (state.activeTab === 'Engine Console') {
    startEngineLogPolling();
  }
}

function init() {
  if (typeof QWebChannel !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, (channel) => {
      state.backend = channel.objects.backend;
      
      state.backend.fetch_audio_devices((devices_json) => {
        state.audioDevices = JSON.parse(devices_json);

        state.backend.get_available_dictionaries((dicts_json) => {
          state.availableDictionaries = JSON.parse(dicts_json);
          
          state.backend.get_settings((json_str) => {
            state.settings = JSON.parse(json_str);
            
            state.backend.fetch_dictation_log((log_json) => {
              state.dictationLog = JSON.parse(log_json);
              
              state.backend.load_dictionary(state.settings.active_dictionary, (dict_json) => {
                state.dictData = JSON.parse(dict_json);
                if (!state.dictData.substitutions) state.dictData.substitutions = {};
                if (!state.dictData.macros) state.dictData.macros = {};
                if (!state.dictData.voice_commands) state.dictData.voice_commands = {};
                
                // Migrate select_all / delete_all to phase: "after" if they exist
                for (const [phrase, cmd] of Object.entries(state.dictData.voice_commands)) {
                  if (cmd.action === 'key' && cmd.keys) {
                    if (cmd.keys.includes('a') && cmd.phase === 'during') {
                      cmd.phase = 'after';
                    }
                  }
                }
                
                render();
              });
            });
          });
        });
      });
    });
  } else {
    console.error("QWebChannel is not loaded.");
  }
}

window.closeConfirmWizardModal = function() {
  state.confirmWizardModal = null;
  render();
};

window.proceedWithWizard = function() {
  const modal = state.confirmWizardModal;
  state.confirmWizardModal = null;
  render();
  
  if (state.backend && modal) {
    if (modal.type === 'personalize') {
      if (state.backend.personalize_wake_word) {
        state.backend.personalize_wake_word(modal.phrase, modal.modelName);
      } else {
        state.backend.start_wake_word_wizard();
      }
    } else {
      state.backend.start_wake_word_wizard();
    }
  }
};

document.addEventListener('DOMContentLoaded', init);
