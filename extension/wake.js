// Runs only on the app's own page (127.0.0.1:7461). It tells the page that the extension is installed in this
// browser, and wakes the extension when the page opens or is about to pull, so that a pull starts at once.
const wake = () => { try { chrome.runtime.sendMessage({ wake: true }).catch(() => {}); } catch (e) { /* extension reloaded */ } };
document.documentElement.dataset.luachExtension = chrome.runtime.getManifest().version;
window.addEventListener("luach-wake", wake);
wake();
