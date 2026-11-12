// ===== PROJECT IDEA GRAPH =====

(() => {
  "use strict";

  const svg = document.getElementById("idea-graph");
  const dataElement = document.getElementById("graph-data");
  if (!svg || !dataElement) return;

  const NS = "http://www.w3.org/2000/svg";
  const WIDTH = 900;
  const HEIGHT = 520;
  const EDGE_COLOR = "#8d9d77";
  const NODE_COLOR = "#55702f";
  const LABEL_BG = "#fcfaf2";
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const createSvg = (tag, attrs = {}) => {
    const element = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) =>
      element.setAttribute(key, String(value)),
    );
    return element;
  };

  let data;
  try {
    data = JSON.parse(dataElement.textContent || "{}");
  } catch (error) {
    svg.innerHTML =
      "<text x='450' y='260' text-anchor='middle'>The graph could not be loaded.</text>";
    return;
  }

  const nodes = Array.isArray(data.nodes) ? data.nodes : [];
  const edges = Array.isArray(data.edges) ? data.edges : [];
  if (!nodes.length) return;

  const nodeIndex = new Map(
    nodes.map((node, index) => [Number(node.id), index]),
  );
  const edgePairs = edges
    .map((edge) => [
      nodeIndex.get(Number(edge.idea_low_id)),
      nodeIndex.get(Number(edge.idea_high_id)),
    ])
    .filter(([a, b]) => a !== undefined && b !== undefined);

  const degrees = new Array(nodes.length).fill(0);
  edgePairs.forEach(([a, b]) => {
    degrees[a] += 1;
    degrees[b] += 1;
  });

  function computeLayout() {
    const count = nodes.length;
    const positions = nodes.map((node, index) => {
      const angle = index * 2.399963;
      const radius = 58 * Math.sqrt(index + 0.5);
      return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
    });
    if (count < 2) return positions;

    const idealDistance = count > 80 ? 145 : 125;
    const iterations =
      count > 250 ? 75 : count > 120 ? 130 : count > 60 ? 190 : 260;
    let temperature = 82;

    for (let iteration = 0; iteration < iterations; iteration += 1) {
      const forceX = new Float64Array(count);
      const forceY = new Float64Array(count);

      for (let first = 0; first < count; first += 1) {
        for (let second = first + 1; second < count; second += 1) {
          let dx = positions[first].x - positions[second].x;
          let dy = positions[first].y - positions[second].y;
          let distance = Math.hypot(dx, dy);
          if (distance < 0.01) {
            dx = (first + 1) * 0.37 - (second + 1) * 0.19;
            dy = (first + 1) * 0.13 - (second + 1) * 0.41;
            distance = Math.max(Math.hypot(dx, dy), 0.01);
          }
          if (distance > 310) continue;
          const repulsion =
            (idealDistance * idealDistance) / (distance * distance);
          forceX[first] += dx * repulsion;
          forceY[first] += dy * repulsion;
          forceX[second] -= dx * repulsion;
          forceY[second] -= dy * repulsion;
        }
      }

      edgePairs.forEach(([first, second]) => {
        const dx = positions[first].x - positions[second].x;
        const dy = positions[first].y - positions[second].y;
        const distance = Math.hypot(dx, dy) || 0.01;
        const attraction = distance / idealDistance;
        forceX[first] -= dx * attraction;
        forceY[first] -= dy * attraction;
        forceX[second] += dx * attraction;
        forceY[second] += dy * attraction;
      });

      for (let index = 0; index < count; index += 1) {
        forceX[index] -= positions[index].x * 0.085;
        forceY[index] -= positions[index].y * 0.085;
        const magnitude = Math.hypot(forceX[index], forceY[index]) || 0.01;
        const step = Math.min(magnitude, temperature);
        positions[index].x += (forceX[index] / magnitude) * step;
        positions[index].y += (forceY[index] / magnitude) * step;
      }
      temperature = Math.max(1.4, temperature * 0.982);
    }
    return positions;
  }

  const positions = computeLayout();
  const nodeRadius = (index) => 15 + Math.min(degrees[index], 6) * 1.55;
  const labelText = (node) => String(node.title || "Untitled idea");
  const visibleLabel = (text) =>
    text.length > 27 ? `${text.slice(0, 26)}…` : text;
  const labelWidth = (text) =>
    clamp(visibleLabel(text).length * 7.1 + 24, 62, 214);

  const world = createSvg("g", { class: "graph-world" });
  const edgeLayer = createSvg("g", { class: "graph-edge-layer" });
  const nodeLayer = createSvg("g", { class: "graph-node-layer" });
  world.append(edgeLayer, nodeLayer);
  svg.replaceChildren(world);

  const edgeElements = [];
  edges.forEach((edge) => {
    const firstIndex = nodeIndex.get(Number(edge.idea_low_id));
    const secondIndex = nodeIndex.get(Number(edge.idea_high_id));
    if (firstIndex === undefined || secondIndex === undefined) return;

    const group = createSvg("g", {
      class: "graph-edge",
      "data-connection-id": edge.id,
      tabindex: "0",
      role: "button",
      "aria-label": `Connection between ${edge.title_a || "first idea"} and ${edge.title_b || "second idea"}`,
    });
    const hitLine = createSvg("line", {
      class: "graph-edge-hit",
      stroke: "transparent",
      "stroke-width": 28,
      "stroke-linecap": "round",
    });
    const visibleLine = createSvg("line", {
      class: "graph-edge-visible",
      stroke: EDGE_COLOR,
      "stroke-width": 2.4,
      "stroke-linecap": "round",
    });
    const midpoint = createSvg("circle", {
      class: "graph-edge-dot",
      r: 4.5,
      fill: EDGE_COLOR,
    });
    const title = createSvg("title");
    title.textContent =
      edge.description ||
      `${edge.title_a || "Idea"} ↔ ${edge.title_b || "Idea"}`;
    group.append(hitLine, visibleLine, midpoint, title);
    edgeLayer.appendChild(group);
    edgeElements.push({
      edge,
      firstIndex,
      secondIndex,
      group,
      hitLine,
      visibleLine,
      midpoint,
    });
  });

  const nodeElements = [];
  nodes.forEach((node, index) => {
    const radius = nodeRadius(index);
    const fullTitle = labelText(node);
    const shortTitle = visibleLabel(fullTitle);
    const backgroundWidth = labelWidth(fullTitle);
    const group = createSvg("g", {
      class: "graph-node",
      "data-node-index": index,
      tabindex: "0",
      role: "link",
      "aria-label": `Open idea: ${fullTitle}`,
    });

    const halo = createSvg("circle", {
      class: "graph-node-halo",
      r: radius + 13,
      fill: "transparent",
    });
    const ring = createSvg("circle", {
      class: "graph-node-ring",
      r: radius + 4,
      fill: LABEL_BG,
      stroke: NODE_COLOR,
      "stroke-width": 2,
    });
    const core = createSvg("circle", {
      class: "graph-node-core",
      r: radius,
      fill: NODE_COLOR,
    });

    const labelPlate = createSvg("rect", {
      class: "graph-node-label-bg",
      x: -backgroundWidth / 2,
      y: radius + 9,
      width: backgroundWidth,
      height: 27,
      rx: 8,
      ry: 8,
      fill: LABEL_BG,
      stroke: "#d8dfcd",
      "stroke-width": 1,
    });
    const label = createSvg("text", {
      class: "graph-node-label",
      x: 0,
      y: radius + 27,
      "text-anchor": "middle",
      "dominant-baseline": "middle",
    });
    label.textContent = shortTitle;

    const tooltip = createSvg("title");
    tooltip.textContent = `${fullTitle}${degrees[index] ? "" : " (not connected)"}`;
    group.append(halo, ring, core, labelPlate, label, tooltip);
    nodeLayer.appendChild(group);
    nodeElements.push(group);
  });

  function updateNode(index) {
    const point = positions[index];
    nodeElements[index].setAttribute(
      "transform",
      `translate(${point.x} ${point.y})`,
    );
  }

  function updateEdge(element) {
    const first = positions[element.firstIndex];
    const second = positions[element.secondIndex];
    [element.hitLine, element.visibleLine].forEach((line) => {
      line.setAttribute("x1", first.x);
      line.setAttribute("y1", first.y);
      line.setAttribute("x2", second.x);
      line.setAttribute("y2", second.y);
    });
    element.midpoint.setAttribute("cx", (first.x + second.x) / 2);
    element.midpoint.setAttribute("cy", (first.y + second.y) / 2);
  }

  const edgesByNode = new Map();
  edgeElements.forEach((element) => {
    [element.firstIndex, element.secondIndex].forEach((index) => {
      if (!edgesByNode.has(index)) edgesByNode.set(index, []);
      edgesByNode.get(index).push(element);
    });
  });
  positions.forEach((_, index) => updateNode(index));
  edgeElements.forEach(updateEdge);

  const view = { x: 0, y: 0, scale: 1 };
  let userInteracted = false;
  const setTransform = () =>
    world.setAttribute(
      "transform",
      `translate(${view.x} ${view.y}) scale(${view.scale})`,
    );

  function fitGraph() {
    const minX = Math.min(
      ...positions.map(
        (point, index) =>
          point.x -
          Math.max(nodeRadius(index), labelWidth(labelText(nodes[index])) / 2),
      ),
    );
    const maxX = Math.max(
      ...positions.map(
        (point, index) =>
          point.x +
          Math.max(nodeRadius(index), labelWidth(labelText(nodes[index])) / 2),
      ),
    );
    const minY = Math.min(
      ...positions.map((point, index) => point.y - nodeRadius(index)),
    );
    const maxY = Math.max(
      ...positions.map((point, index) => point.y + nodeRadius(index) + 46),
    );
    const boundsWidth = Math.max(maxX - minX, 80);
    const boundsHeight = Math.max(maxY - minY, 80);
    const availableWidth = WIDTH - 120;
    const availableHeight = HEIGHT - 100;
    view.scale = clamp(
      Math.min(availableWidth / boundsWidth, availableHeight / boundsHeight),
      0.24,
      1.35,
    );
    view.x = WIDTH / 2 - ((minX + maxX) / 2) * view.scale;
    view.y = HEIGHT / 2 - ((minY + maxY) / 2) * view.scale;
    setTransform();
    userInteracted = false;
  }

  function zoomAt(x, y, factor) {
    const nextScale = clamp(view.scale * factor, 0.18, 3.2);
    const ratio = nextScale / view.scale;
    view.x = x - (x - view.x) * ratio;
    view.y = y - (y - view.y) * ratio;
    view.scale = nextScale;
    setTransform();
    userInteracted = true;
  }

  function clientToView(clientX, clientY) {
    const rect = svg.getBoundingClientRect();
    return {
      x: ((clientX - rect.left) / Math.max(rect.width, 1)) * WIDTH,
      y: ((clientY - rect.top) / Math.max(rect.height, 1)) * HEIGHT,
    };
  }

  function openIdea(index) {
    const node = nodes[index];
    if (!node || !node.edit_url) return;
    const opened = window.open(node.edit_url, "_blank");
    if (opened) {
      try {
        opened.opener = null;
      } catch (error) {}
    } else {
      window.location.href = node.edit_url;
    }
  }

  function selectEdge(id) {
    edgeElements.forEach((element) => {
      const selected = String(element.edge.id) === String(id);
      element.group.classList.toggle("is-selected", selected);
      element.group.setAttribute("aria-pressed", String(selected));
    });
  }

  const edgeDetails = document.getElementById("graph-edge-details");
  const edgeDetailsTitle = document.getElementById("graph-edge-details-title");
  const edgeDetailsBody = document.getElementById("graph-edge-details-body");
  const edgeDetailsClose = document.getElementById("graph-edge-details-close");

  function hideEdgeDetails() {
    if (edgeDetails) edgeDetails.hidden = true;
    selectEdge(null);
  }

  function showEdgeDetails(edgeId) {
    const element = edgeElements.find(
      (item) => String(item.edge.id) === String(edgeId),
    );
    if (!element) return;
    selectEdge(edgeId);
    const edge = element.edge;
    const first = edge.title_a || "First idea";
    const second = edge.title_b || "Second idea";
    if (edgeDetailsTitle)
      edgeDetailsTitle.textContent = `${first} ↔ ${second}`;
    if (edgeDetailsBody) {
      edgeDetailsBody.textContent =
        edge.description || "No connection note has been added.";
    }
    if (edgeDetails) {
      edgeDetails.hidden = false;
      return;
    }
    window.alert(
      `${first} ↔ ${second}\n\n${edge.description || "No connection note has been added."}`,
    );
  }

  edgeDetailsClose?.addEventListener("click", hideEdgeDetails);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && edgeDetails && !edgeDetails.hidden) {
      hideEdgeDetails();
    }
  });

  const pointers = new Map();
  let gesture = null;
  let pinchState = null;

  const distanceBetween = (first, second) =>
    Math.hypot(second.x - first.x, second.y - first.y) || 1;
  const centerBetween = (first, second) => ({
    x: (first.x + second.x) / 2,
    y: (first.y + second.y) / 2,
  });

  svg.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    try {
      svg.setPointerCapture(event.pointerId);
    } catch (error) {}
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (pointers.size === 2) {
      const pair = Array.from(pointers.values()).slice(0, 2);
      pinchState = {
        distance: distanceBetween(pair[0], pair[1]),
        center: centerBetween(pair[0], pair[1]),
      };
      gesture = { mode: "pinch", moved: true };
      svg.classList.add("is-dragging");
      userInteracted = true;
      return;
    }
    if (pointers.size > 2) return;

    const node = event.target.closest(".graph-node");
    const edge = event.target.closest(".graph-edge");
    gesture = {
      mode: node ? "node" : edge ? "edge" : "pan",
      nodeIndex: node ? Number(node.dataset.nodeIndex) : null,
      edgeId: edge ? edge.dataset.connectionId : null,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      moved: false,
    };
  });

  svg.addEventListener("pointermove", (event) => {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (
      gesture &&
      gesture.mode === "pinch" &&
      pointers.size >= 2 &&
      pinchState
    ) {
      const pair = Array.from(pointers.values()).slice(0, 2);
      const center = centerBetween(pair[0], pair[1]);
      const distance = distanceBetween(pair[0], pair[1]);
      const centerView = clientToView(center.x, center.y);
      zoomAt(centerView.x, centerView.y, distance / pinchState.distance);
      const previousCenter = clientToView(
        pinchState.center.x,
        pinchState.center.y,
      );
      const delta = {
        x: centerView.x - previousCenter.x,
        y: centerView.y - previousCenter.y,
      };
      view.x += delta.x;
      view.y += delta.y;
      setTransform();
      pinchState = { distance, center };
      return;
    }

    if (!gesture || gesture.mode === "edge") return;
    const movement = Math.hypot(
      event.clientX - gesture.startX,
      event.clientY - gesture.startY,
    );
    if (!gesture.moved && movement > 6) {
      gesture.moved = true;
      userInteracted = true;
      if (gesture.mode === "pan") svg.classList.add("is-dragging");
    }
    if (!gesture.moved) return;

    const current = clientToView(event.clientX, event.clientY);
    if (gesture.mode === "node") {
      const index = gesture.nodeIndex;
      positions[index].x = (current.x - view.x) / view.scale;
      positions[index].y = (current.y - view.y) / view.scale;
      updateNode(index);
      (edgesByNode.get(index) || []).forEach(updateEdge);
    } else if (gesture.mode === "pan") {
      const previous = clientToView(gesture.lastX, gesture.lastY);
      view.x += current.x - previous.x;
      view.y += current.y - previous.y;
      setTransform();
    }
    gesture.lastX = event.clientX;
    gesture.lastY = event.clientY;
  });

  function endPointer(event, cancelled = false) {
    if (!pointers.has(event.pointerId)) return;
    pointers.delete(event.pointerId);
    if (gesture && gesture.mode === "pinch") {
      if (pointers.size < 2) {
        gesture = null;
        pinchState = null;
      }
      if (!pointers.size) svg.classList.remove("is-dragging");
      return;
    }

    const completed = gesture;
    gesture = null;
    svg.classList.remove("is-dragging");
    if (!completed || cancelled || completed.moved) return;
    if (completed.mode === "node" && completed.nodeIndex !== null)
      openIdea(completed.nodeIndex);
    else if (completed.mode === "edge" && completed.edgeId !== null)
      showEdgeDetails(completed.edgeId);
    if (!pointers.size) pinchState = null;
  }

  svg.addEventListener("pointerup", (event) => endPointer(event, false));
  svg.addEventListener("pointercancel", (event) => endPointer(event, true));
  svg.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const point = clientToView(event.clientX, event.clientY);
      zoomAt(point.x, point.y, event.deltaY < 0 ? 1.12 : 1 / 1.12);
    },
    { passive: false },
  );

  nodeElements.forEach((element, index) => {
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openIdea(index);
      }
    });
  });
  edgeElements.forEach(({ edge, group }) => {
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        showEdgeDetails(edge.id);
      }
    });
  });

  const zoomInButton = document.getElementById("graph-zoom-in");
  const zoomOutButton = document.getElementById("graph-zoom-out");
  const fitButton = document.getElementById("graph-fit");
  const fullscreenButton = document.getElementById("graph-fullscreen");
  const wrapper = svg.closest(".graph-canvas-wrap");

  zoomInButton?.addEventListener("click", () =>
    zoomAt(WIDTH / 2, HEIGHT / 2, 1.28),
  );
  zoomOutButton?.addEventListener("click", () =>
    zoomAt(WIDTH / 2, HEIGHT / 2, 1 / 1.28),
  );
  fitButton?.addEventListener("click", fitGraph);

  if (fullscreenButton && wrapper) {
    fullscreenButton.addEventListener("click", async () => {
      try {
        if (!document.fullscreenElement && wrapper.requestFullscreen)
          await wrapper.requestFullscreen();
        else if (document.fullscreenElement && document.exitFullscreen)
          await document.exitFullscreen();
      } catch (error) {
        window.alert(
          "The browser could not open the graph in full-screen mode.",
        );
      }
    });
  }

  document.addEventListener("fullscreenchange", () => {
    if (fullscreenButton) {
      const expanded = Boolean(
        document.fullscreenElement &&
          wrapper &&
          document.fullscreenElement === wrapper,
      );
      fullscreenButton.innerHTML = expanded
        ? "<i class='ri-fullscreen-exit-line'></i>"
        : "<i class='ri-fullscreen-line'></i>";
      fullscreenButton.setAttribute(
        "aria-label",
        expanded ? "Exit full screen" : "Full screen",
      );
      fullscreenButton.title = expanded ? "Exit full screen" : "Full screen";
    }
  });

  const resizeObserver =
    typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(() => {
          if (!userInteracted) fitGraph();
        })
      : null;
  resizeObserver?.observe(wrapper || svg);

  fitGraph();
})();
