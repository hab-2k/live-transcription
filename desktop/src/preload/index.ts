import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("desktopBridge", {
  backendUrl: process.env["LTD_BACKEND_URL"] ?? process.env["BACKEND_URL"] ?? "",
});
