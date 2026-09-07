import base from './playwright.config';
export default { ...base, webServer: { ...base.webServer, command: 'npm exec -- vite --host 127.0.0.1 --port 1424' } };