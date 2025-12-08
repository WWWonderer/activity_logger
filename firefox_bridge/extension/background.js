const HOST_NAME = "activity_logger_bridge";
let port;

function ensurePort() {
  if (port) {
    return;
  }

  try {
    port = browser.runtime.connectNative(HOST_NAME);
    port.onDisconnect.addListener(() => {
      port = undefined;
    });
  } catch (error) {
    console.error("Failed to connect to native host:", error);
    port = undefined;
  }
}

function shouldTransmit(tab) {
  if (!tab || !tab.url) {
    return false;
  }

  const ignoredSchemes = ["about:", "chrome:", "moz-extension:", "resource:"];
  return !ignoredSchemes.some((prefix) => tab.url.startsWith(prefix));
}

function transmitTab(tab) {
  if (!shouldTransmit(tab)) {
    return;
  }

  ensurePort();
  if (!port) {
    return;
  }

  const message = {
    url: tab.url,
    title: tab.title || "",
    tabId: tab.id,
    windowId: tab.windowId,
    timestamp: new Date().toISOString(),
  };

  try {
    port.postMessage(message);
  } catch (error) {
    console.error("Failed to send message to native host:", error);
    port = undefined;
  }
}

browser.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await browser.tabs.get(activeInfo.tabId);
    transmitTab(tab);
  } catch (error) {
    console.error("Error fetching activated tab:", error);
  }
});

browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tab.active && (changeInfo.url || changeInfo.status === "complete")) {
    transmitTab(tab);
  }
});

browser.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === browser.windows.WINDOW_ID_NONE) {
    return;
  }
  try {
    const tabs = await browser.tabs.query({ active: true, windowId });
    if (tabs.length > 0) {
      transmitTab(tabs[0]);
    }
  } catch (error) {
    console.error("Error fetching focused window tab:", error);
  }
});

browser.runtime.onStartup.addListener(async () => {
  try {
    const tabs = await browser.tabs.query({ active: true, currentWindow: true });
    if (tabs.length > 0) {
      transmitTab(tabs[0]);
    }
  } catch (error) {
    console.error("Error during startup tab query:", error);
  }
});

