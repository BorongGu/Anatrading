import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
export const fixtures=JSON.parse(execFileSync(fileURLToPath(new URL(process.platform==='win32'?'../../.venv/Scripts/python.exe':'../../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('../../tests/group_source_path_fixture_bridge.py',import.meta.url))],{encoding:'utf8',maxBuffer:8*1024*1024}));
