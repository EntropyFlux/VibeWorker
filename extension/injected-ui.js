// injected-ui.js
// Injected into the target page when the AI agent needs manual user interaction.

(function () {
    // Prevent multiple injections
    if (document.getElementById('vibeworker-finish-btn-container')) {
        return;
    }

    const container = document.createElement('div');
    container.id = 'vibeworker-finish-btn-container';
    // Use fixed positioning initially; draggable logic will update this
    container.style.position = 'fixed';
    container.style.right = '20px';
    container.style.bottom = '100px';
    container.style.zIndex = '2147483647'; // Max z-index
    container.style.fontFamily = 'system-ui, -apple-system, sans-serif';

    const shadow = container.attachShadow({ mode: 'open' });

    const style = document.createElement('style');
    style.textContent = `
        :host {
            all: initial; /* Reset all inherited styles */
        }
        .vibe-button {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            color: white;
            border: none;
            border-radius: 9999px;
            padding: 12px 24px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3), 0 0 0 2px rgba(255, 255, 255, 0.2) inset;
            transition: transform 0.2s, box-shadow 0.2s;
            user-select: none;
            -webkit-user-select: none;
            font-family: inherit;
        }
        .vibe-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4), 0 0 0 2px rgba(255, 255, 255, 0.3) inset;
        }
        .vibe-button:active {
            transform: translateY(0);
        }
        .vibe-icon {
            font-size: 18px;
        }
        .drag-handle {
            cursor: grab;
            padding-right: 8px;
            border-right: 1px solid rgba(255, 255, 255, 0.3);
            display: flex;
            align-items: center;
        }
        .drag-handle:active {
            cursor: grabbing;
        }
        .drag-handle svg {
            width: 14px;
            height: 14px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2;
        }
    `;

    const btnWrapper = document.createElement('div');
    btnWrapper.className = 'vibe-button';

    const dragHandle = document.createElement('div');
    dragHandle.className = 'drag-handle';
    dragHandle.innerHTML = '<svg viewBox="0 0 24 24"><path d="M8 6h.01M8 12h.01M8 18h.01M16 6h.01M16 12h.01M16 18h.01" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    const textSpan = document.createElement('span');
    textSpan.textContent = '完成工作';

    const iconSpan = document.createElement('span');
    iconSpan.className = 'vibe-icon';
    iconSpan.textContent = '✅';

    btnWrapper.appendChild(dragHandle);
    btnWrapper.appendChild(iconSpan);
    btnWrapper.appendChild(textSpan);

    shadow.appendChild(style);
    shadow.appendChild(btnWrapper);
    document.body.appendChild(container);

    // Draggable Logic
    let isDragging = false;
    let currentX;
    let currentY;
    let initialX;
    let initialY;
    let xOffset = 0;
    let yOffset = 0;

    dragHandle.addEventListener('mousedown', dragStart);
    document.addEventListener('mouseup', dragEnd);
    document.addEventListener('mousemove', drag);

    function dragStart(e) {
        initialX = e.clientX - xOffset;
        initialY = e.clientY - yOffset;
        isDragging = true;
    }

    function dragEnd(e) {
        initialX = currentX;
        initialY = currentY;
        isDragging = false;
    }

    function drag(e) {
        if (isDragging) {
            e.preventDefault();
            currentX = e.clientX - initialX;
            currentY = e.clientY - initialY;

            xOffset = currentX;
            yOffset = currentY;

            // Use transform for smoother dragging
            container.style.transform = "translate3d(" + currentX + "px, " + currentY + "px, 0)";
        }
    }

    // Click Logic (attach to text/icon, entirely separate from drag handle)
    textSpan.addEventListener('click', finishWork);
    iconSpan.addEventListener('click', finishWork);

    function finishWork() {
        // Send message to background script
        chrome.runtime.sendMessage({ type: 'USER_FINISHED_WORK' }, (response) => {
            console.log('VibeWorker Interaction Finished:', response);
        });

        // Remove the button
        document.body.removeChild(container);
    }
})();
