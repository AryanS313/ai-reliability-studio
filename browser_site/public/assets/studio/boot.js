const base='/assets/studio/';
console.debug = console.log = console.info = () => {};
const statusLabel=document.getElementById('boot-status');
const panel=document.getElementById('boot');
const root=document.getElementById('root');
const retry=document.getElementById('boot-retry');
retry.addEventListener('click',()=>location.reload());
let ready=false;
const fail=()=>{
  if(ready)return;
  statusLabel.textContent='The workspace could not finish loading. Check your connection, then try again.';
  document.getElementById('boot-progress').hidden=true;
  retry.hidden=false;
};
window.addEventListener('error',fail);
window.addEventListener('unhandledrejection',fail);
const stages={
  'Loading Pyodide.':'Preparing your private workspace…',
  'Mounting files.':'Loading the review tools…',
  'Unpacking archives.':'Loading the review tools…',
  'Installing packages.':'Preparing document and report tools…',
  'Loading streamlit package.':'Opening the workspace…',
};
const OriginalWorker=window.Worker;
const runtimeWorkers = new Set();
const runtimeEntryUrls = new Set();
window.addEventListener('pagehide',()=>{root.hidden=true;for(const worker of runtimeWorkers)worker.terminate();runtimeWorkers.clear();for(const url of runtimeEntryUrls)URL.revokeObjectURL(url);runtimeEntryUrls.clear();});
// A restored history entry has DOM but its terminated workers cannot resume.
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
window.Worker=class extends OriginalWorker{
  constructor(script,options){
    const source=new URL(script,location.href);
    let entry=script;
    // Blob workers inherit the document's isolation policy. The static host
    // need not add COEP to the imported module response for this entry point.
    if(source.origin===location.origin && source.pathname===base+'stlite/assets/worker-DB8fls9q.js'){
      if(options?.type!=='module')throw new Error('Unexpected runtime worker type');
      entry=URL.createObjectURL(new Blob(['import '+JSON.stringify(source.href)+';'],{type:'text/javascript'}));
      runtimeEntryUrls.add(entry);
    }
    try{super(entry,options);}catch(error){if(entry!==script){URL.revokeObjectURL(entry);runtimeEntryUrls.delete(entry);}throw error;}
    if(entry!==script){
      const releaseEntry=()=>{URL.revokeObjectURL(entry);runtimeEntryUrls.delete(entry);};
      this.addEventListener('message',releaseEntry,{once:true});
      this.addEventListener('error',releaseEntry,{once:true});
    }
    runtimeWorkers.add(this);
    this.addEventListener('error',(event)=>{fail(); if(location.hostname==='localhost')statusLabel.textContent+=' '+String(event.message || 'Worker failed to load')+' '+String(event.filename || '');});
    this.addEventListener('message',({data})=>{
      if(data?.type==='event:error'){fail(); if(location.hostname==='localhost'){statusLabel.textContent+=' '+String(data.data?.error?.message || data.data?.error || 'Unknown startup error');}}
      if(!ready && data?.type==='event:progress' && stages[data.data?.message])statusLabel.textContent=stages[data.data.message];
    });
  }
};
const observer=new MutationObserver(()=>{
  for(const [selector,label] of [
    ['[data-testid="stSidebarCollapsedControl"] button','Open menu'],
    ['[data-testid="stSidebarCollapseButton"] button','Close menu'],
  ]){
    for(const button of root.querySelectorAll(selector)){
      if(button.getAttribute('aria-label')!==label)button.setAttribute('aria-label',label);
    }
  }
  if(!ready && [...root.querySelectorAll('button')].some(button=>button.textContent.includes('Try sample'))){ready=true;panel.hidden=true;root.hidden=false;}
});
observer.observe(root,{childList:true,subtree:true});
// On narrow screens the sidebar covers the page. Finish navigation by
// dismissing that overlay, so the newly selected page is usable immediately.
const closeMobileMenu=()=>{
  if(window.matchMedia('(max-width: 768px)').matches){
    root.querySelector('[data-testid="stSidebarCollapseButton"] button')?.click();
  }
};
root.addEventListener('change',event=>{
  if(event.target instanceof HTMLInputElement && event.target.type==='radio' && event.target.closest('[data-testid="stSidebar"]'))closeMobileMenu();
});
root.addEventListener('click',event=>{
  const button=event.target instanceof Element ? event.target.closest('[data-testid="stSidebar"] button') : null;
  if(button?.textContent.trim()==='End session and clear my data')closeMobileMenu();
});
const url=path=>new URL(base+path,location.origin).href;
try{
  if(!window.crossOriginIsolated || typeof SharedArrayBuffer==='undefined'){
    statusLabel.textContent='This browser cannot open the private workspace. Open this link in a current version of Chrome to continue.';
    document.getElementById('boot-progress').hidden=true;
    throw new Error('Unsupported browser isolation');
  }
  const {mount}=await import(url('stlite/stlite.js'));
  mount({
    pyodideUrl:url('runtime/pyodide.mjs'),
    prebuiltPackageNames:['numpy','pandas','scikit-learn','sqlite3','ssl','xlrd','beautifulsoup4','lxml','protobuf','pillow','fastparquet','cachetools','altair','pyodide-http','pydantic','pydantic-core','cryptography'],
    requirements:['plotly-5.24.1-py3-none-any.whl','python_dotenv-1.0.1-py3-none-any.whl','pypdf-5.1.0-py3-none-any.whl','python_docx-1.1.2-py3-none-any.whl','striprtf-0.0.29-py3-none-any.whl','openpyxl-3.1.5-py2.py3-none-any.whl','python_pptx-1.0.2-py3-none-any.whl','tenacity-9.1.4-py3-none-any.whl','blinker-1.9.0-py3-none-any.whl','et_xmlfile-2.0.0-py3-none-any.whl','xlsxwriter-3.2.9-py3-none-any.whl'].map(name=>url('wheels/'+name)),
    archives:[{url:url('source.zip'),format:'zip',options:{extractDir:'/app'}},{url:url('provider-packages.zip'),format:'zip',options:{extractDir:'/providers'}}],
    entrypoint:'entry.py',files:{'entry.py':{url:url('entry.py')}},
    streamlitConfig:{'browser.gatherUsageStats':false,'client.toolbarMode':'viewer','server.maxUploadSize':20,'theme.base':'light','theme.primaryColor':'#2563eb','theme.backgroundColor':'#fbfcff','theme.secondaryBackgroundColor':'#f5f7fb','theme.textColor':'#17212f'},
  },root);
}catch(error){if(error.message!=='Unsupported browser isolation')fail();}
