/* Shared browsing labels; these never change model metrics or test averages. */
(function () {
  'use strict';
  const names = {easy: 'Easy', medium: 'Medium', hard: 'Hard'};
  window.rankExampleDifficulty = function (entries) {
    const ordered = [...entries].sort((a,b) => a.reference_ssim-b.reference_ssim || String(a.id).localeCompare(String(b.id)));
    const labels = new Map(ordered.map((e,i) => [e.index, i < Math.ceil(ordered.length/3) ? 'hard' : i >= Math.floor(ordered.length*2/3) ? 'easy' : 'medium']));
    return entries.map(e => ({...e, difficulty: labels.get(e.index)}));
  };
  window.createExampleBrowser = function ({entries, onSelect, current, reference='Im2im'}) {
    const select = document.getElementById('example');
    const nav = select.closest('nav');
    document.getElementById('exampleFilters')?.remove();
    const bar = document.createElement('div');
    bar.id = 'exampleFilters'; bar.className = 'example-filters';
    bar.innerHTML = '<label>Difficulty <select id="difficultyFilter"><option value="all">All images</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>' + '<span id="exampleCategory" class="example-category"></span><span id="filteredCount" class="filter-count"></span>';
    nav.after(bar);
    const difficulty = bar.querySelector('#difficultyFilter');
    const badge = bar.querySelector('#exampleCategory');
    const help = `Relative difficulty: thirds of these displayed images ranked by ${reference} SSIM. Lower SSIM means harder. One shared label for all models; not a physical property of the scene.`;
    difficulty.title = help; badge.title = help;
    const params = new URLSearchParams(location.search);
    if (['easy','medium','hard'].includes(params.get('difficulty'))) difficulty.value=params.get('difficulty');
    let visible = [], busy = false;
    const matches = e => (difficulty.value==='all'||e.difficulty===difficulty.value);
    function update(index) {
      const entry = entries.find(e=>e.index===index);
      badge.textContent = entry ? names[entry.difficulty] : '';
      badge.dataset.difficulty = entry?.difficulty || '';
      select.value = String(index);
      const url = new URL(location.href);
      url.searchParams.set('example', index);
      history.replaceState(null, '', url);
      window.syncDemoNavigation?.();
    }
    function setBusy(value) {
      busy=value;
      for (const node of [difficulty,select,...['previous','next','random'].map(id=>document.getElementById(id))]) if(node) node.disabled=value || (node!==difficulty && !visible.length);
    }
    function apply(navigate) {
      visible=entries.filter(matches);
      select.replaceChildren(...visible.map(e=>new Option(`${e.index+1} · ${e.id} · ${names[e.difficulty]}`,e.index)));
      const count=bar.querySelector('#filteredCount'); count.textContent=`${visible.length} / ${entries.length} images`;
      const url=new URL(location.href);
      if(difficulty.value==='all')url.searchParams.delete('difficulty');else url.searchParams.set('difficulty',difficulty.value);
      url.searchParams.delete('modification');
      history.replaceState(null,'',url);
      const found=visible.find(e=>e.index===current())||visible[0];
      for(const node of document.querySelectorAll('.inputs,#matrix'))node.hidden=!visible.length;
      if(found){update(found.index);if(navigate&&found.index!==current())onSelect(found.index);}
      else{badge.textContent='No matching images';document.getElementById('status').textContent='Choose another difficulty.';}
      setBusy(busy);
      return found?.index;
    }
    const move=step=>{if(busy||!visible.length)return;const position=Math.max(0,visible.findIndex(e=>e.index===current()));onSelect(visible[(position+step+visible.length)%visible.length].index);};
    select.onchange=()=>{if(!busy)onSelect(Number(select.value));};
    document.getElementById('previous').onclick=()=>move(-1);
    document.getElementById('next').onclick=()=>move(1);
    document.getElementById('random').onclick=()=>{if(!busy&&visible.length){const others=visible.filter(e=>e.index!==current());onSelect((others.length?others:visible)[Math.floor(Math.random()*(others.length||visible.length))].index);}};
    difficulty.onchange=()=>apply(true);
    const initialIndex=apply(false);
    return {update,setBusy,initialIndex};
  };
})();
