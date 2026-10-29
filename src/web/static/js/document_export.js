// Export of a print document, from the toolbar of its page.
//
// For Word, the page is laid out by the browser, then sent as it prints:
// paragraphs of styled runs and tables placed on a grid of columns, all the
// lengths in points. The fields hold what was typed in them.

(() => {
    const PX_TO_PT = 0.75;
    const FIELD_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);
    const INLINE_TAGS = new Set([
        'A', 'ABBR', 'B', 'BR', 'CODE', 'EM', 'I', 'IMG', 'INPUT', 'LABEL', 'S',
        'SELECT', 'SMALL', 'SPAN', 'STRONG', 'SUB', 'SUP', 'TEXTAREA', 'U',
    ]);
    const SKIPPED_TAGS = new Set([
        'BUTTON', 'HEAD', 'LINK', 'META', 'NOSCRIPT', 'SCRIPT', 'STYLE', 'TEMPLATE',
    ]);
    const BORDER_STYLES = {solid: 'single', dotted: 'dotted', dashed: 'dashed', double: 'double'};

    // ---------- The print view ----------

    // The rules of the print media, which the export applies over the
    // computed style of the screen.
    function printRules() {
        const rules = [];
        const collect = (ruleList, inPrint) => {
            for (const rule of ruleList) {
                if (rule instanceof CSSMediaRule) {
                    collect(rule.cssRules, inPrint || /\bprint\b/.test(rule.media.mediaText));
                } else if (rule instanceof CSSPageRule) {
                    PAGE_RULES.push(rule);
                } else if (rule instanceof CSSStyleRule && inPrint) {
                    rules.push(rule);
                } else if (rule.cssRules) {
                    collect(rule.cssRules, inPrint);
                }
            }
        };
        for (const sheet of document.styleSheets) {
            try {
                collect(sheet.cssRules, /\bprint\b/.test(sheet.media.mediaText));
            } catch {
                // A style sheet of another origin cannot be read.
            }
        }
        return rules;
    }

    // The @page rules, which give the margins of the pages.
    const PAGE_RULES = [];
    const PRINT_RULES = printRules();
    const styleCache = new WeakMap();

    function styleOf(element) {
        let style = styleCache.get(element);
        if (!style) {
            const computed = getComputedStyle(element);
            const overrides = {};
            for (const rule of PRINT_RULES) {
                let matches = false;
                try {
                    matches = element.matches(rule.selectorText);
                } catch {
                    // A selector the browser does not support.
                }
                if (matches) {
                    for (const property of rule.style) {
                        overrides[property] = rule.style.getPropertyValue(property);
                    }
                }
            }
            style = {
                get: property => overrides[property] ?? computed.getPropertyValue(property),
                overrides: overrides,
                computed: computed,
            };
            styleCache.set(element, style);
        }
        return style;
    }

    function isHidden(element) {
        if (SKIPPED_TAGS.has(element.tagName) || element.hidden) {
            return true;
        }
        if (element.tagName === 'INPUT' && ['hidden', 'button', 'submit', 'reset', 'image'].includes(element.type)) {
            return true;
        }
        const style = styleOf(element);
        return style.get('display') === 'none' || style.get('visibility') === 'hidden';
    }

    function visibleChildren(element) {
        return [...element.childNodes].filter(node =>
            node.nodeType === Node.ELEMENT_NODE ? !isHidden(node)
                : node.nodeType === Node.TEXT_NODE && node.textContent.trim() !== ''
        );
    }

    // ---------- Colours and lengths ----------

    const colorContext = document.createElement('canvas').getContext('2d');

    // The colour as RRGGBB, or null when it is transparent.
    function hexColor(value) {
        if (!value || value === 'transparent') {
            return null;
        }
        colorContext.fillStyle = '#000000';
        colorContext.fillStyle = value;
        const parsed = colorContext.fillStyle;
        if (parsed.startsWith('#')) {
            return parsed.slice(1).toUpperCase();
        }
        const channels = parsed.match(/[\d.]+/g);
        if (!channels || (channels.length > 3 && parseFloat(channels[3]) === 0)) {
            return null;
        }
        return channels.slice(0, 3)
            .map(channel => Math.round(parseFloat(channel)).toString(16).padStart(2, '0'))
            .join('').toUpperCase();
    }

    function isDark(hex) {
        const [red, green, blue] = [0, 2, 4].map(start => parseInt(hex.slice(start, start + 2), 16));
        return 0.299 * red + 0.587 * green + 0.114 * blue < 128;
    }

    // The scale from the page to the Word page, set when the page is laid out.
    let layoutScale = 1;

    function points(value) {
        return Math.round((parseFloat(value) || 0) * PX_TO_PT * layoutScale * 100) / 100;
    }

    // The colour of the text of an element: a colour the print media gives
    // the element, or an ancestor it inherits from, wins over the screen one.
    function textColor(element) {
        const screen = styleOf(element).computed.color;
        for (let ancestor = element; ancestor && ancestor !== document.documentElement; ancestor = ancestor.parentElement) {
            const style = styleOf(ancestor);
            if (style.overrides.color) {
                return hexColor(style.overrides.color);
            }
            if (style.computed.color !== screen) {
                break;
            }
        }
        return hexColor(screen);
    }

    function textDecorations(element) {
        const decorations = new Set();
        for (let ancestor = element; ancestor && ancestor !== document.body; ancestor = ancestor.parentElement) {
            const style = styleOf(ancestor);
            for (const decoration of style.get('text-decoration-line').split(' ')) {
                decorations.add(decoration);
            }
            if (style.computed.display === 'inline-block') {
                break;
            }
        }
        return decorations;
    }

    function border(style, side) {
        const width = parseFloat(style.get(`border-${side}-width`)) || 0;
        const borderStyle = BORDER_STYLES[style.get(`border-${side}-style`)];
        const color = hexColor(style.get(`border-${side}-color`));
        if (!width || !borderStyle || !color) {
            return null;
        }
        return {width: points(width), style: borderStyle, color: color};
    }

    function borders(element) {
        const style = styleOf(element);
        const result = {};
        for (const side of ['top', 'right', 'bottom', 'left']) {
            const sideBorder = border(style, side);
            if (sideBorder) {
                result[side] = sideBorder;
            }
        }
        return Object.keys(result).length ? result : null;
    }

    // The colour filling an element, when it is not white.
    function fillColor(element) {
        const color = hexColor(styleOf(element).get('background-color'));
        return color && color !== 'FFFFFF' ? color : null;
    }

    // ---------- Images ----------

    // The images of the page as PNG data URLs, which Word can show whatever
    // their format, keyed by their source.
    const images = new Map();

    function cssUrl(value) {
        const match = /url\(["']?(.*?)["']?\)/.exec(value || '');
        return match ? match[1] : null;
    }

    async function loadImages() {
        const sources = new Set();
        for (const element of document.body.querySelectorAll('*')) {
            if (element.tagName === 'IMG' && element.currentSrc) {
                sources.add(element.currentSrc);
            }
            const background = cssUrl(styleOf(element).get('background-image'));
            if (background) {
                sources.add(background);
            }
        }
        await Promise.all([...sources].map(async source => {
            const image = new Image();
            image.src = source;
            try {
                await image.decode();
            } catch {
                return;
            }
            const width = image.naturalWidth || 300;
            const height = image.naturalHeight || 150;
            const canvas = document.createElement('canvas');
            const scale = Math.min(2, 2000 / Math.max(width, height));
            canvas.width = Math.max(1, Math.round(width * scale));
            canvas.height = Math.max(1, Math.round(height * scale));
            canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
            try {
                images.set(source, {src: canvas.toDataURL('image/png'), width: width, height: height});
            } catch {
                // An image of another origin cannot be read back.
            }
        }));
    }

    function imageRun(source, width, height) {
        const image = images.get(source);
        if (!image || !width || !height) {
            return null;
        }
        return {type: 'image', src: image.src, width: points(width), height: points(height)};
    }

    // The background image of an element, as it is drawn in its padding box.
    function backgroundImageRun(element) {
        const style = styleOf(element);
        const source = cssUrl(style.get('background-image'));
        const image = source && images.get(source);
        if (!image) {
            return null;
        }
        const box = element.getBoundingClientRect();
        const size = style.get('background-size');
        let scale = 1;
        if (size === 'contain') {
            scale = Math.min(box.width / image.width, box.height / image.height);
        } else if (size === 'cover') {
            scale = Math.max(box.width / image.width, box.height / image.height);
        }
        return imageRun(source, image.width * scale, image.height * scale);
    }

    // ---------- Runs ----------

    const GENERIC_FONT_FAMILIES = new Set([
        'serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui',
        'ui-serif', 'ui-sans-serif', 'ui-monospace', 'ui-rounded', 'math', 'emoji',
    ]);

    // The first font family of an element, unless it is a generic one, which
    // only the browser resolves.
    function fontFamily(element) {
        const family = styleOf(element).computed.fontFamily.split(',')[0].trim().replace(/^["']|["']$/g, '');
        return family && !GENERIC_FONT_FAMILIES.has(family) && !family.startsWith('-') ? family : null;
    }

    function textRun(text, element, sizedOn = element) {
        const style = styleOf(element);
        const decorations = textDecorations(element);
        const transform = style.get('text-transform');
        if (transform === 'uppercase') {
            text = text.toUpperCase();
        } else if (transform === 'lowercase') {
            text = text.toLowerCase();
        }
        const run = {type: 'text', text: text};
        if (parseInt(style.get('font-weight'), 10) >= 600 || style.get('font-weight') === 'bold') {
            run.bold = true;
        }
        if (['italic', 'oblique'].includes(style.get('font-style'))) {
            run.italic = true;
        }
        if (decorations.has('underline')) {
            run.underline = true;
        }
        if (decorations.has('line-through')) {
            run.strike = true;
        }
        run.size = points(styleOf(sizedOn).computed.fontSize);
        const font = fontFamily(element);
        if (font) {
            run.font = font;
        }
        const color = textColor(element);
        if (color && color !== '000000') {
            run.color = color;
        }
        return run;
    }

    // An empty field. It is drawn to the end of the line when it reaches the
    // right of its container, the label before it taking the rest of the line.
    function blankRun(field) {
        const run = {type: 'blank', size: points(styleOf(fieldSizedOn(field)).computed.fontSize)};
        const font = fontFamily(field);
        if (font) {
            run.font = font;
        }
        const container = field.parentElement.getBoundingClientRect();
        const box = field.getBoundingClientRect();
        if (container.right - box.right > 4) {
            run.width = points(box.width);
        }
        return run;
    }

    // A box with no content and a border, such as a drawn check box.
    function markRun(element) {
        const box = element.getBoundingClientRect();
        const style = styleOf(element);
        if (element.childNodes.length || !box.width || box.width > 24 || box.height > 24 || !borders(element)) {
            return null;
        }
        const round = parseFloat(style.get('border-top-left-radius')) >= box.width / 3;
        const background = hexColor(style.get('background-color'));
        const filled = background !== null && isDark(background);
        return textRun(round ? (filled ? '●' : '○') : (filled ? '■' : '□'), element);
    }

    // The text of a field is as large as the text around it, unless the
    // field is given its own size: browsers draw the fields of a page in
    // sizes of their own.
    function fieldSizedOn(field) {
        return field.style.fontSize || !field.parentElement ? field : field.parentElement;
    }

    function fieldRuns(field) {
        if (field.tagName === 'INPUT' && (field.type === 'checkbox' || field.type === 'radio')) {
            const marks = field.type === 'checkbox' ? ['☒', '☐'] : ['◉', '○'];
            return [textRun(field.checked ? marks[0] : marks[1], field, fieldSizedOn(field))];
        }
        let value = field.value;
        if (field.tagName === 'SELECT') {
            value = field.selectedIndex >= 0 ? field.options[field.selectedIndex].text : '';
        }
        if (!value.trim()) {
            return field.closest('td, th') ? [] : [blankRun(field)];
        }
        const runs = [];
        value.split('\n').forEach((line, index) => {
            if (index) {
                runs.push({type: 'break'});
            }
            runs.push(textRun(line, field, fieldSizedOn(field)));
        });
        return runs;
    }

    function inlineRuns(node, runs) {
        if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent.replace(/\s+/g, ' ');
            if (text) {
                runs.push(textRun(text, node.parentElement));
            }
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE || isHidden(node)) {
            return;
        }
        if (node.tagName === 'BR') {
            runs.push({type: 'break'});
        } else if (node.tagName === 'IMG') {
            const box = node.getBoundingClientRect();
            const run = imageRun(node.currentSrc, box.width, box.height);
            if (run) {
                runs.push(run);
            }
        } else if (FIELD_TAGS.has(node.tagName)) {
            runs.push(...fieldRuns(node));
        } else {
            const mark = markRun(node);
            if (mark) {
                runs.push(mark);
                return;
            }
            for (const child of node.childNodes) {
                inlineRuns(child, runs);
            }
        }
    }

    // The runs with the spaces HTML collapses collapsed.
    function collapsed(runs) {
        const result = [];
        let afterSpace = true;
        for (const run of runs) {
            if (run.type === 'text') {
                let text = run.text;
                if (afterSpace) {
                    text = text.replace(/^ /, '');
                }
                if (!text) {
                    continue;
                }
                afterSpace = text.endsWith(' ');
                result.push({...run, text: text});
            } else {
                afterSpace = run.type === 'break';
                result.push(run);
            }
        }
        return result;
    }

    function paragraph(runs, element, spaceBefore) {
        runs = collapsed(runs);
        if (!runs.length) {
            return null;
        }
        const align = styleOf(element).get('text-align');
        const block = {type: 'paragraph', runs: runs};
        if (align === 'center' || align === '-webkit-center') {
            block.align = 'center';
        } else if (align === 'right' || align === 'end' || align === '-webkit-right') {
            block.align = 'right';
        }
        if (spaceBefore) {
            block.space_before = spaceBefore;
        }
        return block;
    }

    // ---------- Blocks ----------

    const BLOCK_SELECTOR = 'div, p, table, section, form, h1, h2, h3, h4, h5, h6, ul, ol';

    function isInlineLevel(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            return true;
        }
        return styleOf(node).computed.display.startsWith('inline') && !node.querySelector(BLOCK_SELECTOR);
    }

    // Fields and images keep their content whatever their display, as the
    // items of a grid or a flex container are displayed as blocks.
    function isAtomic(element) {
        return FIELD_TAGS.has(element.tagName) || element.tagName === 'IMG';
    }

    function marginTop(element) {
        return Math.min(24, points(styleOf(element).computed.marginTop));
    }

    function runsParagraph(node, alignedOn) {
        const runs = [];
        inlineRuns(node, runs);
        return [paragraph(runs, alignedOn)].filter(block => block);
    }

    // The blocks of the content of an element: its runs of inline content
    // become paragraphs, between the blocks of its block children.
    function contentBlocks(element) {
        const children = visibleChildren(element);
        // A field alone in its element is aligned as it is drawn.
        const alignedOn = children.length === 1 && children[0].nodeType === Node.ELEMENT_NODE
            && isAtomic(children[0]) ? children[0] : element;
        const blocks = [];
        let runs = [];
        const flush = () => {
            const block = paragraph(runs, alignedOn, blocks.length ? 0 : marginTop(element));
            if (block) {
                blocks.push(block);
            }
            runs = [];
        };
        for (const child of children) {
            if (isInlineLevel(child)) {
                inlineRuns(child, runs);
            } else {
                flush();
                blocks.push(...elementBlocks(child));
            }
        }
        flush();
        return blocks;
    }

    // The blocks of an element; ``drawBox`` is false when the element is a
    // cell, which draws its border and fill itself.
    function elementBlocks(element, drawBox = true) {
        const style = styleOf(element);
        const display = style.get('display');
        let blocks;
        if (isAtomic(element) || isInlineLevel(element)) {
            blocks = runsParagraph(element, element.parentElement);
        } else if (display === 'table' || display === 'inline-table') {
            blocks = [htmlTable(element)];
        } else if (display === 'grid' || display === 'inline-grid') {
            blocks = rowsTable(element, layoutItems(element));
        } else if (display === 'flex' || display === 'inline-flex') {
            blocks = flexBlocks(element);
        } else {
            blocks = contentBlocks(element);
        }
        blocks = blocks.filter(block => block);
        if (drawBox) {
            blocks = boxed(element, blocks);
        }
        if (['page', 'always', 'left', 'right'].includes(style.get('break-before'))
            || style.get('page-break-before') === 'always') {
            blocks.unshift({type: 'page_break'});
        }
        if (['page', 'always', 'left', 'right'].includes(style.get('break-after'))
            || style.get('page-break-after') === 'always') {
            blocks.push({type: 'page_break'});
        }
        return blocks;
    }

    // The blocks of an element drawn with a border, a fill or a background
    // image, in a cell that draws them.
    function boxed(element, blocks) {
        if (element.tagName === 'TABLE') {
            return spacedAbove(element, blocks);
        }
        const boxBorders = borders(element);
        const fill = fillColor(element);
        const background = backgroundImageRun(element);
        if (!boxBorders && !fill && !background) {
            return blocks;
        }
        const cell = {row: 0, column: 0, blocks: blocks, vertical_align: 'center'};
        const padding = Math.min(24, points(styleOf(element).computed.paddingTop));
        if (padding) {
            cell.padding = padding;
        }
        if (boxBorders) {
            cell.borders = boxBorders;
        }
        if (fill) {
            cell.fill = fill;
        }
        let table;
        if (background) {
            // The image sits in a column of its own, before the content.
            const width = element.getBoundingClientRect().width;
            const imageWidth = Math.max(
                background.width / PX_TO_PT,
                parseFloat(styleOf(element).get('padding-left')) || 0,
            );
            cell.column = 1;
            table = {
                type: 'table',
                columns: [points(imageWidth), points(Math.max(1, width - imageWidth))],
                rows: 1,
                cells: [
                    {row: 0, column: 0, blocks: [{type: 'paragraph', runs: [background]}], vertical_align: 'center'},
                    cell,
                ],
            };
        } else {
            table = {type: 'table', columns: [1], rows: 1, cells: [cell]};
        }
        return spacedAbove(element, [table]);
    }

    // The space above a table is an empty paragraph, a table having none.
    function spacedAbove(element, blocks) {
        const spaceBefore = marginTop(element);
        return spaceBefore >= 8
            ? [{type: 'paragraph', runs: [], space_before: spaceBefore}, ...blocks]
            : blocks;
    }

    // ---------- Tables ----------

    // The items of a grid or a flex container, the text between elements
    // being an item of its own.
    function layoutItems(element) {
        return visibleChildren(element).map(node => {
            if (node.nodeType === Node.ELEMENT_NODE) {
                return {element: node, box: node.getBoundingClientRect()};
            }
            const range = document.createRange();
            range.selectNodeContents(node);
            return {text: node, box: range.getBoundingClientRect()};
        });
    }

    function itemBlocks(item, drawBox = true) {
        if (item.text) {
            return runsParagraph(item.text, item.text.parentElement);
        }
        return elementBlocks(item.element, drawBox);
    }

    function cellOf(item, row, column, columnSpan, rowSpan) {
        const cell = {row: row, column: column, blocks: []};
        if (columnSpan > 1) {
            cell.column_span = columnSpan;
        }
        if (rowSpan > 1) {
            cell.row_span = rowSpan;
        }
        const element = item.element;
        if (!element) {
            cell.blocks = itemBlocks(item);
            return cell;
        }
        const style = styleOf(element);
        const isTableCell = style.get('display') === 'table-cell';
        cell.blocks = isTableCell && !isAtomic(element)
            ? contentBlocks(element)
            : itemBlocks(item, false);
        if (isTableCell) {
            const padding = points(style.computed.paddingTop);
            if (padding) {
                cell.padding = padding;
            }
        }
        const cellBorders = borders(element);
        if (cellBorders) {
            cell.borders = cellBorders;
        }
        const fill = fillColor(element) || (element.tagName === 'TD' || element.tagName === 'TH'
            ? fillColor(element.parentElement) : null);
        if (fill) {
            cell.fill = fill;
        }
        const verticalAlign = style.get('vertical-align');
        if (verticalAlign === 'middle') {
            cell.vertical_align = 'center';
        } else if (verticalAlign === 'bottom') {
            cell.vertical_align = 'bottom';
        }
        return cell;
    }

    // The column edges of a table: where its cells start and end, merged
    // when they are within a pixel of each other.
    function mergedEdges(values) {
        const edges = [];
        for (const value of [...values].sort((a, b) => a - b)) {
            if (!edges.length || value - edges[edges.length - 1] > 1) {
                edges.push(value);
            }
        }
        return edges;
    }

    function edgeIndex(edges, value) {
        let best = 0;
        for (let index = 1; index < edges.length; index++) {
            if (Math.abs(edges[index] - value) < Math.abs(edges[best] - value)) {
                best = index;
            }
        }
        return best;
    }

    // The table of cells placed on rows. The columns of an HTML table end
    // where its cells end; those of a grid or a flex row run from the start
    // of an item to the start of the next one, the gap between them included.
    function tableOfCells(element, placed, rowCount, withGaps) {
        let edges;
        if (withGaps) {
            const box = element.getBoundingClientRect();
            const style = styleOf(element).computed;
            const right = box.right - (parseFloat(style.paddingRight) || 0) - (parseFloat(style.borderRightWidth) || 0);
            edges = mergedEdges([...placed.map(cell => cell.box.left), right]);
        } else {
            edges = mergedEdges(placed.flatMap(cell => [cell.box.left, cell.box.right]));
        }
        if (edges.length < 2) {
            return null;
        }
        const columns = edges.slice(1).map((edge, index) => Math.max(1, points(edge - edges[index])));
        const cells = placed.map(cell => {
            const column = Math.min(edgeIndex(edges, cell.box.left), columns.length - 1);
            const end = withGaps
                ? edges.findIndex(edge => edge > cell.box.right - 1)
                : edgeIndex(edges, cell.box.right);
            const columnSpan = Math.min(columns.length - column, Math.max(1, (end < 0 ? edges.length - 1 : end) - column));
            return cellOf(cell, cell.row, column, columnSpan, cell.rowSpan);
        });
        const table = {type: 'table', columns: columns, rows: Math.max(1, rowCount), cells: cells};
        if (withGaps) {
            // The gaps between the items are in the columns.
            table.cell_margin = 0;
        } else if (placed.length) {
            table.cell_margin = points(styleOf(placed[0].element).computed.paddingLeft);
        }
        const tableBorders = borders(element);
        if (tableBorders) {
            table.borders = tableBorders;
        }
        return table;
    }

    function htmlTable(element) {
        const placed = [];
        [...element.rows].forEach((row, rowIndex) => {
            if (isHidden(row)) {
                return;
            }
            for (const cell of row.cells) {
                if (!isHidden(cell)) {
                    placed.push({
                        element: cell,
                        box: cell.getBoundingClientRect(),
                        row: rowIndex,
                        rowSpan: Math.min(cell.rowSpan || 1, element.rows.length - rowIndex),
                    });
                }
            }
        });
        return tableOfCells(element, placed, element.rows.length, false);
    }

    // Items laid out in rows, as the cells of a table; items in a single
    // column are simply blocks one after the other.
    function rowsTable(element, items) {
        const rows = [];
        for (const item of [...items].sort((a, b) => a.box.top - b.box.top)) {
            const row = rows.find(candidate => Math.abs(candidate.top - item.box.top) < 2);
            if (row) {
                row.items.push(item);
            } else {
                rows.push({top: item.box.top, items: [item]});
            }
        }
        const sequence = () => {
            const blocks = items.flatMap(item => itemBlocks(item));
            const spaceBefore = marginTop(element);
            if (spaceBefore && blocks.length && blocks[0].type === 'paragraph' && !blocks[0].space_before) {
                blocks[0].space_before = spaceBefore;
            }
            return blocks;
        };
        if (rows.every(row => row.items.length === 1)) {
            return sequence();
        }
        const placed = rows.flatMap((row, rowIndex) =>
            row.items.map(item => ({...item, row: rowIndex, rowSpan: 1})));
        const table = tableOfCells(element, placed, rows.length, true);
        if (!table) {
            return sequence();
        }
        if (styleOf(element).computed.display === 'grid') {
            exportGrid(element, table);
        }
        const style = styleOf(element);
        const rowGap = points(style.computed.rowGap);
        // A table has no space above it of its own: the margin of the grid
        // is the space above its first row.
        const spaceBefore = marginTop(element);
        const centred = style.get('display').endsWith('flex') && style.get('align-items') === 'center';
        for (const cell of table.cells) {
            const space = cell.row ? rowGap : spaceBefore;
            if (space) {
                cell.space_before = space;
            }
            if (centred) {
                cell.vertical_align = 'center';
            }
        }
        return [table];
    }

    // ---------- Aligned grids ----------

    // The grids of a container line their columns up on a page as wide as
    // the screen; on a page as narrow as paper, a label that does not wrap
    // widens its column in its own grid only. So the column edges that the
    // grids of a container share on the page are found first, then each set
    // of shared edges is moved to the edge furthest from the start.

    // The fraction of the width of their container at which the column edges
    // of the grids start, on the page as it is shown.
    let pageGridEdges = new Map();
    // The grids laid out for the export, with their table and column edges.
    let exportGrids = [];

    function gridEdges(element) {
        const box = element.getBoundingClientRect();
        const style = styleOf(element).computed;
        const right = box.right - (parseFloat(style.paddingRight) || 0) - (parseFloat(style.borderRightWidth) || 0);
        return mergedEdges([...layoutItems(element).map(item => item.box.left), right]);
    }

    function measurePageGrids() {
        pageGridEdges = new Map();
        exportGrids = [];
        for (const element of document.body.querySelectorAll('*')) {
            const parent = element.parentElement;
            if (!parent || styleOf(element).computed.display !== 'grid' || isHidden(element)) {
                continue;
            }
            const container = parent.getBoundingClientRect();
            if (container.width) {
                pageGridEdges.set(element, gridEdges(element).map(edge => (edge - container.left) / container.width));
            }
        }
    }

    function exportGrid(element, table) {
        const fractions = pageGridEdges.get(element);
        const edges = gridEdges(element);
        if (fractions && fractions.length === edges.length && edges.length === table.columns.length + 1) {
            exportGrids.push({parent: element.parentElement, table: table, fractions: fractions, edges: edges});
        }
    }

    function alignGrids() {
        const byParent = new Map();
        for (const grid of exportGrids) {
            if (!byParent.has(grid.parent)) {
                byParent.set(grid.parent, []);
            }
            byParent.get(grid.parent).push(grid);
        }
        for (const grids of byParent.values()) {
            if (grids.length > 1) {
                alignGridsOf(grids);
            }
        }
        exportGrids = [];
    }

    // The edges at the same fraction of the width of the container, within
    // 2%, are shared.
    function sharedEdges(grids) {
        const edges = grids.flatMap((grid, gridIndex) =>
            grid.fractions.map((fraction, index) => ({grid: gridIndex, index: index, fraction: fraction})))
            .sort((a, b) => a.fraction - b.fraction);
        const groups = [];
        for (const edge of edges) {
            const group = groups[groups.length - 1];
            if (group && edge.fraction - group[0].fraction <= 0.02) {
                group.push(edge);
            } else {
                groups.push([edge]);
            }
        }
        return groups;
    }

    function alignGridsOf(grids) {
        const groups = sharedEdges(grids);
        const groupOf = grids.map(grid => new Array(grid.edges.length));
        groups.forEach((group, groupIndex) => {
            for (const edge of group) {
                groupOf[edge.grid][edge.index] = groupIndex;
            }
        });
        let positions = grids.map(grid => [...grid.edges]);
        for (let pass = 0; pass < 10; pass++) {
            const targets = groups.map(group => Math.max(...group.map(edge => positions[edge.grid][edge.index])));
            let changed = false;
            positions = grids.map((grid, gridIndex) => {
                const last = grid.edges.length - 1;
                return grid.edges.reduce((moved, edge, index) => {
                    // A column keeps the width it needs, the last one taking
                    // what is left up to the end of the container.
                    const minimum = index === 0 ? edge
                        : moved[index - 1] + (index === last ? 1 : grid.edges[index] - grid.edges[index - 1]);
                    const position = index === last ? edge : Math.max(targets[groupOf[gridIndex][index]], minimum);
                    if (position !== positions[gridIndex][index]) {
                        changed = true;
                    }
                    moved.push(position);
                    return moved;
                }, []);
            });
            if (!changed) {
                break;
            }
        }
        grids.forEach((grid, gridIndex) => {
            const moved = positions[gridIndex];
            if (moved.every((position, index) => !index || position > moved[index - 1])) {
                grid.table.columns = moved.slice(1).map((position, index) => Math.max(1, points(position - moved[index])));
            }
        });
    }

    // A flex row is a line of text when its items are all text and fields,
    // and a row of cells otherwise.
    function isTextLine(element, items) {
        if (styleOf(element).get('justify-content').startsWith('space-')) {
            return false;
        }
        return items.every(item => item.text
            || (INLINE_TAGS.has(item.element.tagName) && !item.element.querySelector(BLOCK_SELECTOR)));
    }

    function flexBlocks(element) {
        const items = layoutItems(element);
        if (styleOf(element).get('flex-direction').startsWith('column')) {
            return items.flatMap(item => itemBlocks(item));
        }
        if (isTextLine(element, items)) {
            const runs = [];
            items.forEach((item, index) => {
                if (index) {
                    runs.push({type: 'text', text: ' '});
                }
                inlineRuns(item.element || item.text, runs);
            });
            return [paragraph(runs, element, marginTop(element))];
        }
        return rowsTable(element, items);
    }

    // ---------- Export ----------

    const MM_TO_PX = 96 / 25.4;
    const A4_WIDTH = 210 * MM_TO_PX;
    const DEFAULT_MARGIN = 10 * MM_TO_PX;

    function lengthInPixels(value) {
        const probe = document.createElement('div');
        probe.style.cssText = `position: absolute; visibility: hidden; width: ${value};`;
        document.body.appendChild(probe);
        const width = probe.getBoundingClientRect().width;
        probe.remove();
        return width;
    }

    function inPoints(margins) {
        return Object.fromEntries(Object.entries(margins).map(
            ([side, value]) => [side, Math.round(value * PX_TO_PT * 100) / 100],
        ));
    }

    // The margins of the pages the document prints on, in pixels: those of
    // its last @page rule giving them, 10 mm otherwise.
    function pageMargins() {
        const margins = {top: DEFAULT_MARGIN, right: DEFAULT_MARGIN, bottom: DEFAULT_MARGIN, left: DEFAULT_MARGIN};
        for (const rule of PAGE_RULES) {
            for (const side of Object.keys(margins)) {
                const value = rule.style.getPropertyValue(`margin-${side}`);
                if (value) {
                    margins[side] = lengthInPixels(value);
                }
            }
        }
        return margins;
    }
    // The widest page laid out for the Word file.
    const WIDEST_PAGE = 1000;

    async function wordLayout() {
        await loadImages();
        measurePageGrids();
        // The page is laid out as wide as it is shown, within the width of
        // the Word pages and a width it is not designed past, then scaled down
        // to the Word pages: the text keeps the room it has on the page. It
        // is read before the browser draws again, then given its width back.
        const body = document.body;
        const style = body.getAttribute('style');
        const margins = pageMargins();
        const textWidth = A4_WIDTH - margins.left - margins.right;
        const width = Math.min(WIDEST_PAGE, Math.max(textWidth, body.clientWidth));
        layoutScale = textWidth / width;
        body.style.setProperty('width', `${width}px`, 'important');
        body.style.setProperty('max-width', `${width}px`, 'important');
        body.style.setProperty('margin', '0', 'important');
        body.style.setProperty('padding', '0', 'important');
        try {
            const blocks = contentBlocks(body).filter(block => block);
            alignGrids();
            return {title: document.title || 'document', blocks: blocks, margins: inPoints(margins)};
        } finally {
            layoutScale = 1;
            if (style === null) {
                body.removeAttribute('style');
            } else {
                body.setAttribute('style', style);
            }
        }
    }

    // The page with what was typed in its fields, without its scripts and the
    // toolbar, its links resolved against its address.
    function pageHtml() {
        const copy = document.documentElement.cloneNode(true);
        const fields = document.querySelectorAll('input, textarea, select');
        const copiedFields = copy.querySelectorAll('input, textarea, select');
        fields.forEach((field, index) => {
            const copied = copiedFields[index];
            if (field.tagName === 'TEXTAREA') {
                copied.textContent = field.value;
            } else if (field.tagName === 'SELECT') {
                [...field.options].forEach((option, optionIndex) => {
                    copied.options[optionIndex].toggleAttribute('selected', option.selected);
                });
            } else if (field.type === 'checkbox' || field.type === 'radio') {
                copied.toggleAttribute('checked', field.checked);
            } else {
                copied.setAttribute('value', field.value);
            }
        });
        copy.querySelectorAll('script, .document-export-toolbar').forEach(element => element.remove());
        const base = document.createElement('base');
        base.href = location.href;
        copy.querySelector('head').prepend(base);
        return `<!DOCTYPE html>\n${copy.outerHTML}`;
    }

    function filename(response, fallback) {
        const header = response.headers.get('Content-Disposition') || '';
        const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
        if (encoded) {
            return decodeURIComponent(encoded[1]);
        }
        return fallback;
    }

    // Post what ``content`` gives to ``url``, then download the file of
    // ``mediaType`` it answers.
    async function exportFile(button, url, content, extension, mediaType) {
        button.disabled = true;
        try {
            const body = await content();
            const response = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
            });
            if (!response.ok || response.redirected) {
                throw new Error(`${response.status} ${response.statusText}`);
            }
            if (!(response.headers.get('Content-Type') || '').startsWith(mediaType)) {
                throw new Error(response.headers.get('Content-Type'));
            }
            const blob = await response.blob();
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = filename(response, `${body.title}.${extension}`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(link.href), 10000);
        } catch (error) {
            alert(`${button.dataset.errorMessage}\n${error.message}`);
        } finally {
            button.disabled = false;
        }
    }

    function init() {
        const toolbar = document.querySelector('.document-export-toolbar');
        if (!toolbar) {
            return;
        }
        toolbar.querySelector('.document-export-title').textContent = document.title;
        // The page starts below the toolbar, whatever its notes make its height.
        const reserveRoom = () => document.documentElement.style.setProperty(
            '--document-export-toolbar-height', `${toolbar.offsetHeight}px`,
        );
        reserveRoom();
        new ResizeObserver(reserveRoom).observe(toolbar);
        toolbar.querySelector('[data-export="print"]').addEventListener('click', () => window.print());
        const pdfButton = toolbar.querySelector('[data-export="pdf"]');
        const pdfUrl = toolbar.dataset.pdfExportUrl;
        if (pdfUrl) {
            pdfButton.hidden = false;
            pdfButton.addEventListener('click', () => exportFile(
                pdfButton, pdfUrl,
                () => ({title: document.title || 'document', html: pageHtml(), margins: inPoints(pageMargins())}),
                'pdf', 'application/pdf',
            ));
        }
        const wordButton = toolbar.querySelector('[data-export="word"]');
        const wordUrl = toolbar.dataset.wordExportUrl;
        const hasFields = [...document.body.querySelectorAll('input, textarea, select')]
            .some(field => !toolbar.contains(field));
        if (wordUrl && (hasFields || 'wordExport' in document.body.dataset)) {
            wordButton.hidden = false;
            wordButton.addEventListener('click', () => exportFile(
                wordButton, wordUrl, wordLayout,
                'docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            ));
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
