const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'../..'));
fs.mkdirSync('tmp',{recursive:true});
const testRoot=fs.mkdtempSync(path.resolve('tmp/installer-cleanup-'));
const root=path.join(testRoot,'Sztu Code 测试');
const other=root+'-other';
for(const dir of [root,other]){fs.mkdirSync(path.join(dir,'resources/runtime'),{recursive:true});fs.copyFileSync(process.execPath,path.join(dir,'resources/runtime/node.exe'));}
fs.copyFileSync(process.execPath,path.join(root,'sztucode-desktop.exe'));
const children=[];
const launch=p=>{const child=spawn(p,['-e','setInterval(()=>{},1000)'],{windowsHide:true,stdio:'ignore'});children.push(child);return child;};
(async()=>{try{
 const targets=[launch(path.join(root,'sztucode-desktop.exe')),launch(path.join(root,'resources/runtime/node.exe')),launch(path.join(root,'resources/runtime/node.exe'))];
 const unrelated=launch(path.join(other,'resources/runtime/node.exe'));
 await new Promise(r=>setTimeout(r,500));
 const result=spawnSync(path.resolve('desktop/src-tauri/target/installer/stop-runtime.exe'),[root],{windowsHide:true});
 assert.equal(result.status,0);
 await new Promise(r=>setTimeout(r,100));
 for(const child of targets)assert.notEqual(child.exitCode,null,'target must exit');
 assert.equal(unrelated.exitCode,null,'other installation must remain alive');
 assert.equal(spawnSync(path.resolve('desktop/src-tauri/target/installer/stop-runtime.exe'),[root],{windowsHide:true}).status,0);
 assert.equal(spawnSync(path.resolve('desktop/src-tauri/target/installer/stop-runtime.exe'),['C:\\'],{windowsHide:true}).status,1);
 console.log('PASS: main + 2 runtime processes stopped; other directory Node preserved; repeated cleanup safe; drive root rejected; Unicode/spaces supported');
}finally{children.forEach(c=>c.kill());}})().catch(e=>{console.error(e);process.exitCode=1;});
