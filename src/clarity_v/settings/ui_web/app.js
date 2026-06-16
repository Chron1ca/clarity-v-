const state = {
  backend: null,
  settings: null,
  activeTab: 'General',
  dictData: { substitutions: {} },
  audioDevices: [],
  availableDictionaries: [],
};

function rgbToHex(arr) {
  if (!arr || arr.length < 3) return "#ffffff";
  const r = arr[0].toString(16).padStart(2, '0');
  const g = arr[1].toString(16).padStart(2, '0');
  const b = arr[2].toString(16).padStart(2, '0');
  return `#${r}${g}${b}`;
}

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b, 255];
}

function updateSetting(key, value) {
  state.settings[key] = value;
  render();
}

function renderGeneralTab() {
  const s = state.settings;
  const devs = state.audioDevices.map(d => `
    <option value="${d.index}" ${s.audio_device_index === d.index ? 'selected' : ''}>${d.name}</option>
  `).join('');

  return `
    <div class="card">
      <div class="form-group">
        <label class="label">Microphone Device</label>
        <select class="input-field" onchange="updateSetting('audio_device_index', parseInt(this.value))">
          <option value="-1" ${s.audio_device_index === null || s.audio_device_index === -1 ? 'selected' : ''}>Default System Device</option>
          ${devs}
        </select>
      </div>
      
      <div class="flex-between" style="margin-top: 24px;">
        <span class="label" style="margin:0;">Play Sounds</span>
        <label class="toggle-switch">
          <input type="checkbox" ${s.sound_enabled ? 'checked' : ''} onchange="updateSetting('sound_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>

      <div class="flex-between" style="margin-top: 16px;">
        <span class="label" style="margin:0;">Enable Dictation Log</span>
        <label class="toggle-switch">
          <input type="checkbox" ${s.dictation_log_enabled ? 'checked' : ''} onchange="updateSetting('dictation_log_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
    </div>
    
    <div class="card">
      <div class="form-group">
        <label class="label">Min Recording Seconds</label>
        <div style="display: flex; gap: 16px; align-items: center;">
          <input type="range" class="range-slider" min="0" max="2" step="any" value="${s.min_recording_seconds}" 
                 oninput="updateSetting('min_recording_seconds', parseFloat(this.value))" style="flex:1;">
          <input type="number" class="input-field" style="width: 80px;" min="0" step="0.1" value="${Number(s.min_recording_seconds).toFixed(2)}"
                 onchange="updateSetting('min_recording_seconds', parseFloat(this.value))">
        </div>
      </div>
      
      <div class="form-group" style="margin-top: 24px;">
        <label class="label">Silence to Stop (seconds)</label>
        <div style="display: flex; gap: 16px; align-items: center;">
          <input type="range" class="range-slider" min="0" max="3" step="any" value="${s.silence_seconds_to_stop}"
                 oninput="updateSetting('silence_seconds_to_stop', parseFloat(this.value))" style="flex:1;">
          <input type="number" class="input-field" style="width: 80px;" min="0" step="0.1" value="${Number(s.silence_seconds_to_stop).toFixed(2)}"
                 onchange="updateSetting('silence_seconds_to_stop', parseFloat(this.value))">
        </div>
      </div>
      
      <div class="form-group" style="margin-top: 24px;">
        <label class="label">Commit Window (seconds)</label>
        <div style="display: flex; gap: 16px; align-items: center;">
          <input type="range" class="range-slider" min="0" max="60" step="any" value="${s.commit_window_seconds}"
                 oninput="updateSetting('commit_window_seconds', parseFloat(this.value))" style="flex:1;">
          <input type="number" class="input-field" style="width: 80px;" min="0" step="0.1" value="${Number(s.commit_window_seconds).toFixed(2)}"
                 onchange="updateSetting('commit_window_seconds', parseFloat(this.value))">
        </div>
      </div>
    </div>
  `;
}

// Voice Commands Key Catcher
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
};

window.addVoiceCommand = function() {
  const phrase = document.getElementById("new_vc_phrase").value.trim().toLowerCase();
  const bind = document.getElementById("new_vc_bind").value.trim();
  if (!phrase || !bind) return alert("Phrase and Shortcut cannot be empty.");
  if (!state.settings.dictionary_keybinds) state.settings.dictionary_keybinds = {};
  state.settings.dictionary_keybinds[phrase] = bind;
  render();
};

window.deleteVoiceCommand = function(phrase) {
  delete state.settings.dictionary_keybinds[phrase];
  render();
};

function renderVoiceCommandsTab() {
  const binds = state.settings.dictionary_keybinds || {};
  let html = `<div class="card"><p style="color: var(--text-muted); font-size: 14px;">Voice Commands trigger specific keyboard shortcuts when spoken.</p></div>`;
  
  html += `
    <div class="card" style="border: 1px solid var(--primary); background: rgba(56, 189, 248, 0.05); margin-bottom: 24px;">
      <div style="display: flex; gap: 16px; align-items: flex-end;">
        <div style="flex:1;">
          <label class="label">New Phrase</label>
          <input id="new_vc_phrase" class="input-field" placeholder="e.g. copy that">
        </div>
        <div style="flex:1;">
          <label class="label">Press Shortcut</label>
          <input id="new_vc_bind" class="input-field" placeholder="Click and press keys" onkeydown="captureKey(event)">
        </div>
        <div>
          <button class="btn btn-save" style="padding: 10px 24px;" onclick="addVoiceCommand()">Add</button>
        </div>
      </div>
    </div>
  `;

  for (const [phrase, keybind] of Object.entries(binds)) {
    html += `
      <div class="card" style="display: flex; gap: 16px; align-items: center; margin-bottom: 8px;">
        <div style="flex:1;">
          <input class="input-field" value="${phrase}" readonly style="border: none; background: transparent; padding: 0;">
        </div>
        <div style="flex:1;">
          <input class="input-field" value="${keybind}" readonly style="border: none; background: transparent; padding: 0; color: var(--primary); font-family: monospace;">
        </div>
        <div>
          <button class="btn" style="background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; color: #ef4444; padding: 8px 16px;" onclick="deleteVoiceCommand('${phrase}')">Delete</button>
        </div>
      </div>
    `;
  }
  return html;
}

function renderColorsTab() {
  const s = state.settings;
  const colors = [
    { key: 'color_idle', label: 'Idle Color' },
    { key: 'color_recording', label: 'Recording Color' },
    { key: 'color_processing', label: 'Processing Color' },
    { key: 'color_commit_waiting', label: 'Commit Waiting Color' },
    { key: 'color_error', label: 'Error Color' },
  ];

  let html = `<div class="card grid-2">`;
  colors.forEach(c => {
    html += `
      <div class="form-group flex-between">
        <label class="label" style="margin:0;">${c.label}</label>
        <input type="color" class="color-picker" value="${rgbToHex(s[c.key])}" 
               onchange="updateSetting('${c.key}', hexToRgb(this.value))">
      </div>
    `;
  });
  html += `</div>`;
  return html;
}

// Dictionary Edit
window.addDictionaryEntry = function() {
  const phrase = document.getElementById("new_dict_phrase").value;
  const repl = document.getElementById("new_dict_repl").value;
  if (!phrase || !repl) return alert("Original phrase and replacement cannot be empty.");
  if (!state.dictData.substitutions) state.dictData.substitutions = {};
  state.dictData.substitutions[phrase] = repl;
  render();
};

window.deleteDictionaryEntry = function(phrase) {
  delete state.dictData.substitutions[phrase];
  render();
};

window.onActiveDictionaryChange = function(name) {
  state.settings.active_dictionary = name;
  state.backend.load_dictionary(name, (dict_json) => {
    state.dictData = JSON.parse(dict_json);
    if (!state.dictData.substitutions) state.dictData.substitutions = {};
    render();
  });
};

function renderDictionaryTab() {
  const activeDict = state.settings.active_dictionary || 'default';
  const subs = state.dictData.substitutions || {};
  
  const dictOptions = state.availableDictionaries.map(d => `
    <option value="${d}" ${d === activeDict ? 'selected' : ''}>${d}</option>
  `).join('');

  let cardsHtml = `
    <div class="card" style="border: 1px solid var(--primary); background: rgba(56, 189, 248, 0.05); margin-bottom: 24px;">
      <div style="display: flex; gap: 16px; align-items: flex-end;">
        <div style="flex:1;">
          <label class="label">Original Phrase</label>
          <input id="new_dict_phrase" class="input-field" placeholder="e.g. gonna">
        </div>
        <div style="flex:1;">
          <label class="label">Replacement</label>
          <input id="new_dict_repl" class="input-field" placeholder="e.g. going to">
        </div>
        <div>
          <button class="btn btn-save" style="padding: 10px 24px;" onclick="addDictionaryEntry()">Add</button>
        </div>
      </div>
    </div>
  `;

  for (const [phrase, repl] of Object.entries(subs)) {
    cardsHtml += `
      <div class="card" style="display: flex; gap: 16px; align-items: center; margin-bottom: 8px;">
        <div style="flex:1;">
          <input class="input-field" value="${phrase}" readonly style="border: none; background: transparent; padding: 0;">
        </div>
        <div style="flex:1;">
          <input class="input-field" value="${repl}" readonly style="border: none; background: transparent; padding: 0; color: var(--primary);">
        </div>
        <div>
          <button class="btn" style="background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; color: #ef4444; padding: 8px 16px;" onclick="deleteDictionaryEntry('${phrase}')">Delete</button>
        </div>
      </div>
    `;
  }
  
  return `
    <div class="card" style="max-width: 400px; margin-bottom: 32px;">
      <div class="form-group" style="margin: 0;">
        <label class="label">Active Dictionary</label>
        <select class="input-field" onchange="onActiveDictionaryChange(this.value)">
          ${dictOptions}
        </select>
        <p style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">Select a dictionary to load and edit its substitutions.</p>
      </div>
    </div>
    
    <div>
      <h3 style="margin-bottom: 16px; font-size: 16px; font-weight: 500;">Substitutions</h3>
      ${cardsHtml}
    </div>
  `;
}

// Wake Words
window.addWakeWord = function() {
  const name = document.getElementById("new_ww_name").value.trim();
  const path = document.getElementById("new_ww_path").value.trim();
  const role = document.getElementById("new_ww_role").value.trim();
  const threshold = parseFloat(document.getElementById("new_ww_thresh").value);
  
  if (!name || !path || !role) return alert("Fields cannot be empty.");
  
  state.settings.wake_words.push({
    name: name,
    path: path,
    threshold: threshold,
    role: role
  });
  render();
};

window.deleteWakeWord = function(index) {
  state.settings.wake_words.splice(index, 1);
  render();
};

window.updateWakeWordValue = function(index, key, val) {
  state.settings.wake_words[index][key] = val;
  if(key !== 'threshold') render(); // don't re-render while dragging slider
};

function renderWakeWordsTab() {
  const words = state.settings.wake_words || [];
  
  let html = `
    <div class="card" style="border: 1px solid var(--primary); background: rgba(56, 189, 248, 0.05); margin-bottom: 32px;">
      <h3 style="margin-bottom: 16px; font-size: 16px; font-weight: 500;">Add New Wake Word</h3>
      <div class="grid-2" style="gap: 16px;">
        <div class="form-group">
          <label class="label">Name</label>
          <input id="new_ww_name" class="input-field" placeholder="e.g. computer">
        </div>
        <div class="form-group">
          <label class="label">Role</label>
          <select id="new_ww_role" class="input-field">
            <option value="start">start</option>
            <option value="stop">stop</option>
          </select>
        </div>
        <div class="form-group" style="grid-column: span 2;">
          <label class="label">Model Path</label>
          <input id="new_ww_path" class="input-field" placeholder="e.g. wake_words/computer.onnx">
        </div>
        <div class="form-group" style="grid-column: span 2;">
          <label class="label">Sensitivity Threshold</label>
          <input id="new_ww_thresh" type="range" class="range-slider" min="0" max="1" step="0.01" value="0.5">
        </div>
      </div>
      <button class="btn btn-save" style="margin-top: 16px; width: 100%;" onclick="addWakeWord()">Add Wake Word</button>
    </div>
  `;

  words.forEach((w, i) => {
    html += `
      <div class="card" style="margin-bottom: 16px;">
        <div style="display: flex; gap: 24px; align-items: stretch;">
          <div style="flex: 2; display: flex; flex-direction: column; gap: 12px;">
            <div>
              <label class="label">Name</label>
              <input class="input-field" value="${w.name}" onchange="updateWakeWordValue(${i}, 'name', this.value)">
            </div>
            <div>
              <label class="label">Model Path</label>
              <input class="input-field" value="${w.path}" onchange="updateWakeWordValue(${i}, 'path', this.value)">
            </div>
          </div>
          
          <div style="flex: 1; display: flex; flex-direction: column; gap: 12px;">
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
                <input type="number" class="input-field" style="width: 70px;" min="0" max="1" step="0.01" value="${Number(w.threshold).toFixed(2)}"
                       onchange="updateWakeWordValue(${i}, 'threshold', parseFloat(this.value)); this.previousElementSibling.value=this.value;">
              </div>
            </div>
          </div>
          
          <div style="display: flex; align-items: center;">
            <button class="btn" style="background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; color: #ef4444; height: 100%; padding: 0 24px;" onclick="deleteWakeWord(${i})">Delete</button>
          </div>
        </div>
      </div>
    `;
  });
  return html;
}

function saveSettings() {
  if (state.backend) {
    state.backend.save_settings(JSON.stringify(state.settings));
    if (state.dictData && state.dictData.substitutions) {
      state.backend.save_dictionary(state.settings.active_dictionary || 'default', JSON.stringify(state.dictData, null, 4));
    }
    
    // Smooth toast notification
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

function render() {
  if (!state.settings) {
    document.body.innerHTML = '<div style="padding: 20px; display: flex; align-items: center; justify-content: center; height: 100vh; color: var(--text-muted);">Loading configuration...</div>';
    return;
  }

  const tabs = ['General', 'Dictionary', 'Voice Commands', 'Wake Words', 'Colors'];
  let contentHtml = '';
  if (state.activeTab === 'Dictionary') contentHtml = renderDictionaryTab();
  else if (state.activeTab === 'General') contentHtml = renderGeneralTab();
  else if (state.activeTab === 'Voice Commands') contentHtml = renderVoiceCommandsTab();
  else if (state.activeTab === 'Colors') contentHtml = renderColorsTab();
  else if (state.activeTab === 'Wake Words') contentHtml = renderWakeWordsTab();

  const sidebarHtml = tabs.map(tab => `
    <div class="tab-item ${state.activeTab === tab ? 'active' : ''}" data-tab="${tab}">
      ${tab}
    </div>
  `).join('');

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
        <h1 style="font-size: 20px; font-weight: 600; color: #fff; margin-bottom: 32px; padding-left: 16px;">Clarity</h1>
        ${sidebarHtml}
      </div>
      <div class="content-area" style="position: relative; overflow-y: auto;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; padding-bottom: 16px; border-bottom: 1px solid var(--border);">
          <h2 class="page-title" style="margin: 0; font-size: 24px; font-weight: 500;">${state.activeTab}</h2>
          <button class="btn btn-save" style="padding: 10px 24px; font-weight: 600;" onclick="saveSettings()">Save Changes</button>
        </div>
        <div style="padding-bottom: 60px;">
          ${contentHtml}
        </div>
      </div>
    </div>
  `;

  document.querySelectorAll('.tab-item').forEach(el => {
    el.addEventListener('click', (e) => {
      state.activeTab = e.currentTarget.getAttribute('data-tab');
      render();
    });
  });
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
            
            state.backend.load_dictionary(state.settings.active_dictionary, (dict_json) => {
              state.dictData = JSON.parse(dict_json);
              if (!state.dictData.substitutions) state.dictData.substitutions = {};
              render();
            });
          });
        });
      });
    });
  } else {
    console.error("QWebChannel is not loaded.");
  }
}

document.addEventListener('DOMContentLoaded', init);
