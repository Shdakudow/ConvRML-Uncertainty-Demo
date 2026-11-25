"use strict";

function initUnpaired() {
  const base = "./exports/unpaired";
  const pictures = document.querySelector("#wgt-pictures");
  const videos = document.querySelector("#wgt-video");
  const capture = pictures.querySelector("#capture-select");
  const nextPicture = pictures.querySelector("#capture-next");
  const sigma = pictures.querySelector("#wgt-blur");
  const sequence = videos.querySelector("#sequence-select");
  const nextVideo = videos.querySelector("#sequence-next");
  const play = videos.querySelector("#vid-play");
  const slider = videos.querySelector("#vid-frame");
  const label = videos.querySelector("#vid-frame-label");
  const pictureStatus = pictures.querySelector("[role=status]");
  const videoStatus = videos.querySelector("[role=status]");
  const signed = document.querySelector("#signedWidth");
  let redrawVideo, stills, player, pictureRequest = 0, videoRequest = 0;

  async function manifest(name) {
    const response = await fetch(base + "/" + name + ".json?v=q-width-1");
    if (!response.ok) throw Error("Could not load " + name);
    return response.json();
  }

  function meanWidth(meta, index, modelIdx) {
    return meta.models[modelIdx] === "qutcc" && !signed.checked
      ? meta.qutccAbsWidths[index] : meta.widths[index][modelIdx];
  }

  function showWidths(panel, meta, index) {
    panel.querySelectorAll(".wgt-method").forEach(card => {
      const model = card.querySelector("canvas").dataset.method;
      const width = meanWidth(meta, index, meta.models.indexOf(model));
      card.querySelector(".wgt-avg-width").textContent = "Mean width " + width.toFixed(4);
    });
  }

  async function showPicture() {
    const request = ++pictureRequest;
    pictureStatus.textContent = "Loading picture…";
    try {
      if (!stills) {
        const meta = await manifest("stills");
        if (request !== pictureRequest) return;
        stills = meta;
        capture.replaceChildren(...meta.names.map(n => new Option(n.replaceAll("_"," "), n)));
        nextPicture.disabled = capture.length < 2;
      }
      const name = capture.value;
      const folder = base + "/stills/" + name + "/";
      const canvases = [...pictures.querySelectorAll("canvas")];
      const images = await Promise.all(canvases.map(async canvas => {
        const {method, kind} = canvas.dataset;
        const prefix = method === "qutcc" && !signed.checked ? "abs-width-" : "width-";
        const key = kind === "width" ? prefix + sigma.value : kind;
        const modelFolder = method === "deepensemble" ? "ensemble" : method;
        const image = new Image();
        image.src = folder + (method ? modelFolder + "/" + key + ".png" : "input.png");
        await image.decode();
        return image;
      }));
      if (request !== pictureRequest) return;
      canvases.forEach((c,i) => c.getContext("2d").drawImage(images[i],0,0));
      showWidths(pictures, stills, stills.names.indexOf(name));
      pictureStatus.textContent = "";
    } catch (error) {
      if (request === pictureRequest) pictureStatus.textContent = "Could not load picture.";
    }
  }

  async function showVideo() {
    const request = ++videoRequest;
    if (player) {
      player.pause();
      player.removeAttribute("src");
      player.load();
    }
    const video = document.createElement("video");
    player = video;
    video.muted = true;
    video.playsInline = true;
    play.disabled = slider.disabled = true;
    label.textContent = "– / –";
    videoStatus.textContent = "Loading sequence…";
    try {
      const id = sequence.value;
      const meta = await manifest(id);
      if (request !== videoRequest) return;
      const tiles = [...videos.querySelectorAll("canvas")].map(canvas => {
        const {method,kind} = canvas.dataset;
        const column = method ? ["prediction","width","upper","lower"].indexOf(kind) : 0;
        const row = method ? meta.models.indexOf(method) + 1 : 0;
        return {ctx:canvas.getContext("2d"), x:480*column, y:270*row, canvas};
      });
      // Cache label nodes once so draw() never queries the DOM.
      const widthNodes = [...videos.querySelectorAll("#vid-layout .wgt-method")].map(card => ({
        node: card.querySelector(".wgt-avg-width"),
        modelIdx: meta.models.indexOf(card.querySelector("[data-method]").dataset.method),
      }));
      function draw(time) {
        if (request !== videoRequest || video.readyState < 2) return;
        const frame = Math.min(meta.names.length-1, Math.floor(time*meta.fps + 0.0001));
        // Skip canvases hidden by display:none (bound-figures when toggle is off).
        tiles.forEach(({ctx,x,y,canvas}) => {
          if (canvas.offsetParent === null) return;
          const useAbsoluteTile = canvas.dataset.method === "qutcc" &&
            canvas.dataset.kind === "width" && !signed.checked;
          ctx.drawImage(video,x,useAbsoluteTile ? 0 : y,480,270,0,0,480,270);
        });
        slider.value = frame;
        label.textContent = (frame+1) + " / " + meta.names.length;
        widthNodes.forEach(({node,modelIdx}) => {
          node.textContent = "Mean width " + meanWidth(meta,frame,modelIdx).toFixed(4);
        });
      }
      redrawVideo = () => draw((Number(slider.value) + 0.25) / meta.fps);
      function tick() {
        if (request !== videoRequest) return;
        video.requestVideoFrameCallback((_,info) => { draw(info.mediaTime); tick(); });
      }
      if (video.requestVideoFrameCallback) tick();
      else video.ontimeupdate = () => draw(video.currentTime);
      video.onloadeddata = () => {
        if (request !== videoRequest) return;
        play.disabled = slider.disabled = false;
        videoStatus.textContent = "";
        draw(0);
      };
      video.onseeked = () => draw(video.currentTime);
      video.onplay = () => { play.textContent = "Pause"; };
      video.onpause = () => { if (request === videoRequest) play.textContent = "Play"; };
      video.onerror = () => { if (request === videoRequest) videoStatus.textContent = "Could not load video."; };
      play.textContent = "Play";
      play.onclick = async () => {
        if (video.paused) {
          try { await video.play(); } catch { videoStatus.textContent = "Playback unavailable."; }
        } else video.pause();
      };
      slider.max = meta.names.length-1;
      slider.oninput = () => { video.pause(); video.currentTime = (Number(slider.value)+0.25)/meta.fps; };
      video.preload = "auto";
      video.src = base + "/" + id + ".mp4?v=q-width-1";
    } catch {
      if (request === videoRequest) videoStatus.textContent = "Could not load sequence.";
    }
  }

  function activate() {
    const visible = document.querySelector("#tab-without-gt").classList.contains("active");
    if (visible && videos.classList.contains("active")) {
      if (!player) showVideo();
      else redrawVideo?.();
    } else {
      player?.pause();
      if (visible && !stills) showPicture();
    }
  }
  nextPicture.onclick = () => {
    capture.selectedIndex = (capture.selectedIndex + 1) % capture.length;
    showPicture();
  };
  nextVideo.onclick = () => {
    sequence.selectedIndex = (sequence.selectedIndex + 1) % sequence.length;
    showVideo();
  };
  signed.addEventListener("change", () => {
    if (stills || pictureRequest) showPicture();
    redrawVideo?.();
  });
  capture.onchange = sigma.onchange = showPicture;
  videos.querySelector("#vid-show-bounds").addEventListener("click", () => redrawVideo?.());
  sequence.onchange = showVideo;
  document.querySelectorAll(".page-tab, .subtab").forEach(btn => btn.addEventListener("click", activate));
}
