(() => {
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';


  // Smooth page-to-page navigation: short fade + top progress, without blocking normal browser behavior.
  const transitionOverlay = document.querySelector('[data-page-transition]');
  const progressLine = document.querySelector('[data-page-progress]');
  const showPageTransition = (label='Sahifa yuklanmoqda...') => {
    if (transitionOverlay) {
      const text = transitionOverlay.querySelector('.page-transition-text');
      if (text) text.textContent = label;
      transitionOverlay.classList.add('active');
    }
    document.body.classList.add('navigating');
    if (progressLine) {
      progressLine.style.opacity='1';
      progressLine.style.width='68%';
      setTimeout(()=>{ if(progressLine) progressLine.style.width='84%'; }, 90);
    }
  };
  const finishPageTransition = () => {
    document.body.classList.remove('navigating');
    if (transitionOverlay) transitionOverlay.classList.remove('active');
    if (progressLine) {
      progressLine.style.width='100%';
      setTimeout(()=>{ if(progressLine){progressLine.style.opacity='0';progressLine.style.width='0';}}, 180);
    }
  };
  const shouldTransitionLink = (link) => {
    if (!link) return false;
    if (link.hasAttribute('download') || link.target==='_blank' || link.hasAttribute('data-no-transition')) return false;
    const href = link.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('javascript:')) return false;
    let url; try { url = new URL(href, window.location.href); } catch { return false; }
    return url.origin === window.location.origin && url.pathname !== window.location.pathname || (url.origin === window.location.origin && url.search !== window.location.search);
  };

  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href]');
    if (!link || e.defaultPrevented || e.button !== 0) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (!shouldTransitionLink(link)) return;
    showPageTransition('Sahifa yuklanmoqda...');
  }, true);

  document.addEventListener('submit', (e) => {
    const form=e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.hasAttribute('data-chunk-upload') || form.hasAttribute('data-no-transition') || form.getAttribute('target')==='_blank') return;
    if (form.dataset.uploading==='1') return;
    showPageTransition('So‘rov yuborilmoqda...');
  }, true);

  window.addEventListener('pageshow', finishPageTransition);
  window.addEventListener('pagehide', () => {
    // Keep the transition visible while the browser swaps documents.
    if (transitionOverlay) transitionOverlay.classList.add('active');
    if (progressLine) progressLine.style.width='100%';
  });

  document.addEventListener('click', (e) => {
    const toggle = e.target.closest('[data-user-menu]'); const pop = $('[data-user-popover]');
    if (toggle && pop) { pop.classList.toggle('open'); return; }
    if (pop && !e.target.closest('.user-menu')) pop.classList.remove('open');
    const mobileToggle = e.target.closest('[data-mobile-nav]');
    const mobilePanel = $('[data-mobile-nav-panel]');
    if (mobileToggle && mobilePanel) { mobilePanel.classList.toggle('open'); return; }
    if (mobilePanel && !e.target.closest('[data-mobile-nav-panel]')) mobilePanel.classList.remove('open');
    const dismiss = e.target.closest('[data-dismiss]'); if (dismiss) dismiss.closest('.toast-card')?.remove();
    const smartBack = e.target.closest('[data-smart-back]');
    if (smartBack) { const sameOrigin = document.referrer && document.referrer.startsWith(window.location.origin); if (sameOrigin && history.length > 1) history.back(); else window.location.href='/'; }
    if (e.target.closest('[data-sidebar-toggle]')) document.body.classList.add('sidebar-open');
    if (e.target.closest('[data-sidebar-close]')) document.body.classList.remove('sidebar-open');
  });
  document.addEventListener('keydown', (e) => { if ((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('.top-search input')?.focus();} if(e.key==='Escape'){ $('[data-user-popover]')?.classList.remove('open'); $('[data-mobile-nav-panel]')?.classList.remove('open'); document.body.classList.remove('sidebar-open'); }});
  $$('[data-auto-dismiss]').forEach(el => setTimeout(() => el.remove(), 5200));
  $$('[data-confirm]').forEach(el => el.addEventListener('click', e => { if(!window.confirm(el.getAttribute('data-confirm') || 'Davom etasizmi?')) e.preventDefault(); }));

  $$('input[type=file][data-preview]').forEach(input => input.addEventListener('change', () => {
    const target=document.getElementById(input.dataset.preview), file=input.files?.[0];
    if(target&&file&&file.type.startsWith('image/')){target.style.display='block'; target.src=URL.createObjectURL(file);}
    const fileName=input.closest('[data-dropzone]')?.querySelector('[data-file-name]'); if(fileName) fileName.innerHTML = '<span>Tanlangan fayl:</span> ' + (file ? file.name : '—');
    if (file) { const box = input.dataset.progressBox ? document.getElementById(input.dataset.progressBox) : null; if (box) setProgress(box, 0, 'Fayl tanlandi · ' + file.name); }
  }));
  $$('[data-dropzone]').forEach(zone => { const input=$('input[type=file]',zone); ['dragenter','dragover'].forEach(ev=>zone.addEventListener(ev,e=>{e.preventDefault();zone.classList.add('dragging')})); ['dragleave','drop'].forEach(ev=>zone.addEventListener(ev,e=>{e.preventDefault();zone.classList.remove('dragging')})); zone.addEventListener('drop',e=>{if(input&&e.dataTransfer.files.length){input.files=e.dataTransfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}}); zone.addEventListener('click',e=>{if(!e.target.closest('input')) input?.click();}); });
  $$('[data-copy]').forEach(btn=>btn.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(btn.dataset.copy);btn.textContent='Nusxa olindi';setTimeout(()=>btn.textContent='Nusxa olish',1200)}catch(e){}}));
  $$('[data-scroll-to]').forEach(btn=>btn.addEventListener('click',()=>document.getElementById(btn.dataset.scrollTo)?.scrollIntoView({behavior:'smooth',block:'start'})));

  async function jsonRequest(url, options={}){
    const headers = Object.assign({'X-CSRFToken':csrf()}, options.headers||{}); const res=await fetch(url,Object.assign({},options,{headers})); const data=await res.json().catch(()=>({success:false,message:'Server javobi noto‘g‘ri'})); if(!res.ok||!data.success) throw new Error(data.message||'Yuklashda xato'); return data;
  }
  async function uploadFile(file, kind, onProgress){
    const init=await jsonRequest('/api/uploads/chunk/init',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,size:file.size,mime:file.type,kind})});
    const id=init.data.upload_id, chunkSize=init.data.chunk_size, total=init.data.total_chunks; let sent=0;
    for(let i=0;i<total;i++){
      const slice=file.slice(i*chunkSize,Math.min(file.size,(i+1)*chunkSize)); const fd=new FormData(); fd.append('upload_id',id);fd.append('chunk_index',String(i));fd.append('chunk',slice,file.name+'.part');
      await fetch('/api/uploads/chunk',{method:'POST',headers:{'X-CSRFToken':csrf()},body:fd}).then(async r=>{const d=await r.json();if(!r.ok||!d.success)throw new Error(d.message||'Qism yuklanmadi')}); sent+=slice.size; if(onProgress)onProgress(sent/file.size,i+1,total);
    }
    await jsonRequest('/api/uploads/chunk/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({upload_id:id,total_chunks:total})});
    return id;
  }
  function setProgress(box, percent, meta){ if(!box)return; box.classList.add('active'); const bar=box.querySelector('.progress-bar'); if(bar)bar.style.width=(percent*100).toFixed(1)+'%'; const pct=box.querySelector('[data-progress-percent]'); if(pct)pct.textContent=Math.round(percent*100)+'%'; const m=box.querySelector('[data-progress-meta]'); if(m)m.textContent=meta||''; }
  $$('form[data-chunk-upload]').forEach(form=>form.addEventListener('submit', async (e)=>{
    if(form.dataset.uploading==='1') return; e.preventDefault(); form.dataset.uploading='1';
    const overlay=$('[data-async-overlay]'); overlay?.classList.add('active'); const files=[...form.querySelectorAll('input[type=file][data-upload-kind]')].filter(i=>i.files?.[0]); const totalBytes=files.reduce((n,i)=>n+i.files[0].size,0); let done=0;
    try{
      for(const input of files){ const box=document.getElementById(input.dataset.progressBox); const token=await uploadFile(input.files[0],input.dataset.uploadKind,(fraction)=>{const overall=(done+input.files[0].size*fraction)/Math.max(totalBytes,1);setProgress(box,fraction,`Yuklanmoqda · ${input.files[0].name}`); const global=document.querySelector('[data-global-progress]'); if(global){global.style.width=(overall*100).toFixed(1)+'%';}}); const hidden=document.createElement('input');hidden.type='hidden';hidden.name=input.dataset.tokenName;hidden.value=token;form.appendChild(hidden); const chosenName=input.closest('[data-dropzone]')?.querySelector('[data-file-name]'); if(chosenName) chosenName.innerHTML='<span>Yuklandi:</span> ' + input.files[0].name; const completedBox=document.getElementById(input.dataset.progressBox); if(completedBox) setProgress(completedBox, 1, 'Fayl tayyor · ' + input.files[0].name); done+=input.files[0].size;input.disabled=true; }
      form.dataset.uploading='2'; form.submit();
    }catch(err){ form.dataset.uploading='0'; overlay?.classList.remove('active'); alert(err.message||'Fayl yuklashda xato yuz berdi.'); }
  }));
})();
