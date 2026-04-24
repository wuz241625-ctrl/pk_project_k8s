((win, doc) => {
  win.addEventListener(
    "load",
    function () {
      FastClick.attach(doc.body || doc.getElementsByTagName("body")[0]);
    },
    false
  );

  doc.documentElement.addEventListener(
    "touchmove",
    function (e) {
      if (e.touches.length > 1) {
        e.preventDefault();
      }
    },
    { passive: false }
  );

  const resize = () => {
    const winWidth = doc.documentElement.clientWidth;

    if (winWidth <= 750) {
      doc.documentElement.style.fontSize = winWidth / 3.75 + "px";
      return;
    }

    if (winWidth <= 1024) {
      doc.documentElement.style.fontSize = winWidth / 10.24 + "px";
      return;
    }

    doc.documentElement.style.fontSize = winWidth / 19.2 + "px";
  };

  resize();

  win.addEventListener("resize", resize, false);
})(window, document);
