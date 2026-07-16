/* Säker uttrycksparser för WB-JSON v1 — VÅR kod (inte motorns).

   LLM:en får inte skicka JS-funktioner, så grafernas plots bär en
   uttryckssträng (`expr: "x^2 - 2*x + 1"`) i stället för motorns `fn`.
   Den här parsern kompilerar strängen till en riktig funktion via en
   AST-interpretator — ingen eval, ingen new Function, bara whitelist:
   tal, x, + - * / ^ ( ), sin cos tan sqrt log ln exp abs, pi, e.

   Grammatiken speglas serversidigt i app/whiteboard_spec.py
   (validate_expr) — håll dem i synk.

     WBExpr.compile('sin(2*x)')  -> function (x) { ... }   (kastar Error
                                     med svensk felbeskrivning vid syntaxfel)
*/
(function () {
  'use strict';

  var FUNCTIONS = {
    sin: Math.sin, cos: Math.cos, tan: Math.tan, sqrt: Math.sqrt,
    log: Math.log10 || function (v) { return Math.log(v) / Math.LN10; },
    ln: Math.log, exp: Math.exp, abs: Math.abs,
  };
  var CONSTANTS = { pi: Math.PI, e: Math.E };

  var TOKEN_RE = /\s*(?:(\d+(?:\.\d+)?)|([a-zA-Z]+)|([+\-*/^()]))/y;

  function tokenize(src) {
    var tokens = [];
    var pos = 0;
    while (pos < src.length) {
      TOKEN_RE.lastIndex = pos;
      var m = TOKEN_RE.exec(src);
      if (!m || TOKEN_RE.lastIndex === pos) {
        var rest = src.slice(pos).replace(/^\s+/, '');
        if (!rest) break;
        throw new Error("otillåtet tecken '" + rest[0] + "'");
      }
      var ident = m[2];
      if (ident !== undefined && ident !== 'x' &&
          !(ident in FUNCTIONS) && !(ident in CONSTANTS)) {
        throw new Error("okänt namn '" + ident + "'");
      }
      tokens.push(m[1] !== undefined ? { t: 'num', v: parseFloat(m[1]) }
        : ident !== undefined ? { t: 'name', v: ident }
        : { t: 'op', v: m[3] });
      pos = TOKEN_RE.lastIndex;
    }
    return tokens;
  }

  /* AST-noder: {op:'num',v} {op:'x'} {op:'const',v} {op:'call',f,arg}
     {op:'+'|'-'|'*'|'/'|'^', a, b} {op:'neg', a} */
  function parse(tokens) {
    var i = 0;
    function peekOp() {
      var tok = tokens[i];
      return tok && tok.t === 'op' ? tok.v : null;
    }
    function take() {
      if (i >= tokens.length) throw new Error('uttrycket slutar oväntat');
      return tokens[i++];
    }
    function expr() {
      var node = term();
      while (peekOp() === '+' || peekOp() === '-') {
        var op = take().v;
        node = { op: op, a: node, b: term() };
      }
      return node;
    }
    function term() {
      var node = unary();
      while (peekOp() === '*' || peekOp() === '/') {
        var op = take().v;
        node = { op: op, a: node, b: unary() };
      }
      return node;
    }
    function unary() {
      if (peekOp() === '-') { take(); return { op: 'neg', a: unary() }; }
      return power();
    }
    function power() {
      var node = atom();
      if (peekOp() === '^') { take(); return { op: '^', a: node, b: unary() }; }
      return node;
    }
    function atom() {
      var tok = take();
      if (tok.t === 'num') return { op: 'num', v: tok.v };
      if (tok.t === 'name') {
        if (tok.v === 'x') return { op: 'x' };
        if (tok.v in CONSTANTS) return { op: 'num', v: CONSTANTS[tok.v] };
        // funktion — kräver parentes
        var open = take();
        if (open.t !== 'op' || open.v !== '(') {
          throw new Error("'" + tok.v + "' måste följas av '('");
        }
        var arg = expr();
        var close = take();
        if (close.t !== 'op' || close.v !== ')') throw new Error("')' saknas");
        return { op: 'call', f: tok.v, arg: arg };
      }
      if (tok.v === '(') {
        var node = expr();
        var end = take();
        if (end.t !== 'op' || end.v !== ')') throw new Error("')' saknas");
        return node;
      }
      throw new Error("oväntat '" + tok.v + "'");
    }
    var root = expr();
    if (i !== tokens.length) {
      throw new Error("oväntat '" + String(tokens[i].v) + "' efter uttryckets slut");
    }
    return root;
  }

  function evaluate(node, x) {
    switch (node.op) {
      case 'num': return node.v;
      case 'x': return x;
      case 'neg': return -evaluate(node.a, x);
      case '+': return evaluate(node.a, x) + evaluate(node.b, x);
      case '-': return evaluate(node.a, x) - evaluate(node.b, x);
      case '*': return evaluate(node.a, x) * evaluate(node.b, x);
      case '/': return evaluate(node.a, x) / evaluate(node.b, x);
      case '^': return Math.pow(evaluate(node.a, x), evaluate(node.b, x));
      case 'call': return FUNCTIONS[node.f](evaluate(node.arg, x));
    }
    return NaN;
  }

  window.WBExpr = {
    compile: function (src) {
      var tokens = tokenize(String(src == null ? '' : src));
      if (!tokens.length) throw new Error('tomt uttryck');
      var ast = parse(tokens);
      return function (x) { return evaluate(ast, x); };
    },
  };
})();
