// The only CodeMirror surface the Vault editor uses (kit/app/static/vault-editor.js).
// Markdown is built from @lezer/markdown directly: @codemirror/lang-markdown would pull
// in the HTML, CSS and JavaScript language packs for embedded code, which a note
// editor with syntax highlighting (not live preview) does not need.
import {EditorState, EditorSelection, Compartment, Transaction} from '@codemirror/state';
import {EditorView, keymap, drawSelection, highlightActiveLine, placeholder, highlightSpecialChars} from '@codemirror/view';
import {history, defaultKeymap, historyKeymap, indentWithTab, undo, redo, undoDepth, redoDepth} from '@codemirror/commands';
import {Language, LanguageSupport, defineLanguageFacet, syntaxHighlighting, HighlightStyle} from '@codemirror/language';
import {tags} from '@lezer/highlight';
import {parser, GFM} from '@lezer/markdown';

const facet = defineLanguageFacet({commentTokens: {block: {open: '<!--', close: '-->'}}});
const markdownLanguage = new Language(facet, parser.configure([GFM]), [], 'markdown');
const markdown = () => new LanguageSupport(markdownLanguage);

// Colours come from the page's CSS variables so light and dark themes both hold.
const noteHighlight = HighlightStyle.define([
  {tag: tags.heading1, fontWeight: '700', fontSize: '1.3em'},
  {tag: tags.heading2, fontWeight: '700', fontSize: '1.15em'},
  {tag: [tags.heading3, tags.heading4, tags.heading5, tags.heading6], fontWeight: '700'},
  {tag: tags.strong, fontWeight: '700'},
  {tag: tags.emphasis, fontStyle: 'italic'},
  {tag: tags.strikethrough, textDecoration: 'line-through'},
  {tag: [tags.link, tags.url], color: 'var(--accent, #3b6fd8)'},
  {tag: tags.monospace, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace'},
  {tag: [tags.processingInstruction, tags.meta, tags.contentSeparator], color: 'var(--muted, #888)'},
  {tag: tags.quote, fontStyle: 'italic', color: 'var(--muted, #888)'},
]);

window.TamanitomoCodeMirror = Object.freeze({
  EditorState, EditorSelection, Compartment, Transaction,
  EditorView, keymap, drawSelection, highlightActiveLine, placeholder, highlightSpecialChars,
  history, defaultKeymap, historyKeymap, indentWithTab, undo, redo, undoDepth, redoDepth,
  syntaxHighlighting, noteHighlight, markdown,
});
