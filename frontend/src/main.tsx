import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

// Guard against the classic React + browser-translation crash. Google Translate (and some
// extensions) swap out text nodes; React later calls removeChild/insertBefore on a node
// whose parent has changed and throws NotFoundError, blanking the whole page. Making these
// two DOM methods no-op instead of throwing when the parent doesn't match keeps the app
// alive no matter what mutates the DOM. Harmless for normal React operation.
if (typeof Node === 'function' && Node.prototype) {
  const origRemoveChild = Node.prototype.removeChild;
  Node.prototype.removeChild = function <T extends Node>(this: Node, child: T): T {
    if (child.parentNode !== this) return child;
    return origRemoveChild.call(this, child) as T;
  };
  const origInsertBefore = Node.prototype.insertBefore;
  Node.prototype.insertBefore = function <T extends Node>(
    this: Node, newNode: T, referenceNode: Node | null,
  ): T {
    if (referenceNode && referenceNode.parentNode !== this) return newNode;
    return origInsertBefore.call(this, newNode, referenceNode) as T;
  };
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
