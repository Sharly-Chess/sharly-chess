{% raw %}
(function(f){if(typeof exports==="object"&&typeof module!=="undefined"){module.exports=f()}else if(typeof define==="function"&&define.amd){define([],f)}else{var g;if(typeof window!=="undefined"){g=window}else if(typeof global!=="undefined"){g=global}else if(typeof self!=="undefined"){g=self}else{g=this}g.Polyglot = f()}})(function(){var define,module,exports;return (function(){function r(e,n,t){function o(i,f){if(!n[i]){if(!e[i]){var c="function"==typeof require&&require;if(!f&&c)return c(i,!0);if(u)return u(i,!0);var a=new Error("Cannot find module '"+i+"'");throw a.code="MODULE_NOT_FOUND",a}var p=n[i]={exports:{}};e[i][0].call(p.exports,function(r){var n=e[i][1][r];return o(n||r)},p,p.exports,r,e,n,t)}return n[i].exports}for(var u="function"==typeof require&&require,i=0;i<t.length;i++)o(t[i]);return o}return r})()({1:[function(require,module,exports){
	// shim for using process in browser
	var process = module.exports = {};

	// cached from whatever global is present so that test runners that stub it
	// don't break things.  But we need to wrap it in a try catch in case it is
	// wrapped in strict mode code which doesn't define any globals.  It's inside a
	// function because try/catches deoptimize in certain engines.

	var cachedSetTimeout;
	var cachedClearTimeout;

	function defaultSetTimout() {
		throw new Error('setTimeout has not been defined');
	}
	function defaultClearTimeout () {
		throw new Error('clearTimeout has not been defined');
	}
	(function () {
		try {
			if (typeof setTimeout === 'function') {
				cachedSetTimeout = setTimeout;
			} else {
				cachedSetTimeout = defaultSetTimout;
			}
		} catch (e) {
			cachedSetTimeout = defaultSetTimout;
		}
		try {
			if (typeof clearTimeout === 'function') {
				cachedClearTimeout = clearTimeout;
			} else {
				cachedClearTimeout = defaultClearTimeout;
			}
		} catch (e) {
			cachedClearTimeout = defaultClearTimeout;
		}
	} ())
	function runTimeout(fun) {
		if (cachedSetTimeout === setTimeout) {
			//normal enviroments in sane situations
			return setTimeout(fun, 0);
		}
		// if setTimeout wasn't available but was latter defined
		if ((cachedSetTimeout === defaultSetTimout || !cachedSetTimeout) && setTimeout) {
			cachedSetTimeout = setTimeout;
			return setTimeout(fun, 0);
		}
		try {
			// when when somebody has screwed with setTimeout but no I.E. maddness
			return cachedSetTimeout(fun, 0);
		} catch(e){
			try {
				// When we are in I.E. but the script has been evaled so I.E. doesn't trust the global object when called normally
				return cachedSetTimeout.call(null, fun, 0);
			} catch(e){
				// same as above but when it's a version of I.E. that must have the global object for 'this', hopfully our context correct otherwise it will throw a global error
				return cachedSetTimeout.call(this, fun, 0);
			}
		}


	}
	function runClearTimeout(marker) {
		if (cachedClearTimeout === clearTimeout) {
			//normal enviroments in sane situations
			return clearTimeout(marker);
		}
		// if clearTimeout wasn't available but was latter defined
		if ((cachedClearTimeout === defaultClearTimeout || !cachedClearTimeout) && clearTimeout) {
			cachedClearTimeout = clearTimeout;
			return clearTimeout(marker);
		}
		try {
			// when when somebody has screwed with setTimeout but no I.E. maddness
			return cachedClearTimeout(marker);
		} catch (e){
			try {
				// When we are in I.E. but the script has been evaled so I.E. doesn't  trust the global object when called normally
				return cachedClearTimeout.call(null, marker);
			} catch (e){
				// same as above but when it's a version of I.E. that must have the global object for 'this', hopfully our context correct otherwise it will throw a global error.
				// Some versions of I.E. have different rules for clearTimeout vs setTimeout
				return cachedClearTimeout.call(this, marker);
			}
		}



	}
	var queue = [];
	var draining = false;
	var currentQueue;
	var queueIndex = -1;

	function cleanUpNextTick() {
		if (!draining || !currentQueue) {
			return;
		}
		draining = false;
		if (currentQueue.length) {
			queue = currentQueue.concat(queue);
		} else {
			queueIndex = -1;
		}
		if (queue.length) {
			drainQueue();
		}
	}

	function drainQueue() {
		if (draining) {
			return;
		}
		var timeout = runTimeout(cleanUpNextTick);
		draining = true;

		var len = queue.length;
		while(len) {
			currentQueue = queue;
			queue = [];
			while (++queueIndex < len) {
				if (currentQueue) {
					currentQueue[queueIndex].run();
				}
			}
			queueIndex = -1;
			len = queue.length;
		}
		currentQueue = null;
		draining = false;
		runClearTimeout(timeout);
	}

	process.nextTick = function (fun) {
		var args = new Array(arguments.length - 1);
		if (arguments.length > 1) {
			for (var i = 1; i < arguments.length; i++) {
				args[i - 1] = arguments[i];
			}
		}
		queue.push(new Item(fun, args));
		if (queue.length === 1 && !draining) {
			runTimeout(drainQueue);
		}
	};

	// v8 likes predictible objects
	function Item(fun, array) {
		this.fun = fun;
		this.array = array;
	}
	Item.prototype.run = function () {
		this.fun.apply(null, this.array);
	};
	process.title = 'browser';
	process.browser = true;
	process.env = {};
	process.argv = [];
	process.version = ''; // empty string to avoid regexp issues
	process.versions = {};

	function noop() {}

	process.on = noop;
	process.addListener = noop;
	process.once = noop;
	process.off = noop;
	process.removeListener = noop;
	process.removeAllListeners = noop;
	process.emit = noop;
	process.prependListener = noop;
	process.prependOnceListener = noop;

	process.listeners = function (name) { return [] }

	process.binding = function (name) {
		throw new Error('process.binding is not supported');
	};

	process.cwd = function () { return '/' };
	process.chdir = function (dir) {
		throw new Error('process.chdir is not supported');
	};
	process.umask = function() { return 0; };

	},{}],2:[function(require,module,exports){
	//     (c) 2012-2018 Airbnb, Inc.
	//
	//     polyglot.js may be freely distributed under the terms of the BSD
	//     license. For all licensing information, details, and documentation:
	//     http://airbnb.github.com/polyglot.js
	//
	//
	// Polyglot.js is an I18n helper library written in JavaScript, made to
	// work both in the browser and in Node. It provides a simple solution for
	// interpolation and pluralization, based off of Airbnb's
	// experience adding I18n functionality to its Backbone.js and Node apps.
	//
	// Polylglot is agnostic to your translation backend. It doesn't perform any
	// translation; it simply gives you a way to manage translated phrases from
	// your client- or server-side JavaScript application.
	//

	'use strict';

	var entries = require('object.entries');
	var warning = require('warning');
	var has = require('hasown');

	var warn = function warn(message) {
	  warning(false, message);
	};

	var defaultReplace = String.prototype.replace;
	var split = String.prototype.split;

	// #### Pluralization methods
	// The string that separates the different phrase possibilities.
	var delimiter = '||||';

	var russianPluralGroups = function (n) {
	  var lastTwo = n % 100;
	  var end = lastTwo % 10;
	  if (lastTwo !== 11 && end === 1) {
		return 0;
	  }
	  if (2 <= end && end <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) {
		return 1;
	  }
	  return 2;
	};

	var defaultPluralRules = {
	  // Mapping from pluralization group plural logic.
	  pluralTypes: {
		arabic: function (n) {
		  // http://www.arabeyes.org/Plural_Forms
		  if (n < 3) { return n; }
		  var lastTwo = n % 100;
		  if (lastTwo >= 3 && lastTwo <= 10) return 3;
		  return lastTwo >= 11 ? 4 : 5;
		},
		bosnian_serbian: russianPluralGroups,
		chinese: function () { return 0; },
		croatian: russianPluralGroups,
		french: function (n) { return n >= 2 ? 1 : 0; },
		german: function (n) { return n !== 1 ? 1 : 0; },
		russian: russianPluralGroups,
		lithuanian: function (n) {
		  if (n % 10 === 1 && n % 100 !== 11) { return 0; }
		  return n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19) ? 1 : 2;
		},
		czech: function (n) {
		  if (n === 1) { return 0; }
		  return (n >= 2 && n <= 4) ? 1 : 2;
		},
		polish: function (n) {
		  if (n === 1) { return 0; }
		  var end = n % 10;
		  return 2 <= end && end <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 1 : 2;
		},
		icelandic: function (n) { return (n % 10 !== 1 || n % 100 === 11) ? 1 : 0; },
		slovenian: function (n) {
		  var lastTwo = n % 100;
		  if (lastTwo === 1) {
			return 0;
		  }
		  if (lastTwo === 2) {
			return 1;
		  }
		  if (lastTwo === 3 || lastTwo === 4) {
			return 2;
		  }
		  return 3;
		},
		romanian: function (n) {
		  if (n === 1) { return 0; }
		  var lastTwo = n % 100;
		  if (n === 0 || (lastTwo >= 2 && lastTwo <= 19)) { return 1; }
		  return 2;
		},
		ukrainian: russianPluralGroups
	  },

	  // Mapping from pluralization group to individual language codes/locales.
	  // Will look up based on exact match, if not found and it's a locale will parse the locale
	  // for language code, and if that does not exist will default to 'en'
	  pluralTypeToLanguages: {
		arabic: ['ar'],
		bosnian_serbian: ['bs-Latn-BA', 'bs-Cyrl-BA', 'srl-RS', 'sr-RS'],
		chinese: ['id', 'id-ID', 'ja', 'ko', 'ko-KR', 'lo', 'ms', 'th', 'th-TH', 'zh'],
		croatian: ['hr', 'hr-HR'],
		german: ['fa', 'da', 'de', 'en', 'es', 'fi', 'el', 'he', 'hi-IN', 'hu', 'hu-HU', 'it', 'nl', 'no', 'pt', 'sv', 'tr'],
		french: ['fr', 'tl', 'pt-br'],
		russian: ['ru', 'ru-RU'],
		lithuanian: ['lt'],
		czech: ['cs', 'cs-CZ', 'sk'],
		polish: ['pl'],
		icelandic: ['is', 'mk'],
		slovenian: ['sl-SL'],
		romanian: ['ro'],
		ukrainian: ['uk', 'ua']
	  }
	};

	function langToTypeMap(mapping) {
	  var ret = {};
	  var mappingEntries = entries(mapping);
	  for (var i = 0; i < mappingEntries.length; i += 1) {
		var type = mappingEntries[i][0];
		var langs = mappingEntries[i][1];
		for (var j = 0; j < langs.length; j += 1) {
		  ret[langs[j]] = type;
		}
	  }
	  return ret;
	}

	function pluralTypeName(pluralRules, locale) {
	  var langToPluralType = langToTypeMap(pluralRules.pluralTypeToLanguages);
	  return langToPluralType[locale]
		|| langToPluralType[split.call(locale, /-/, 1)[0]]
		|| langToPluralType.en;
	}

	function pluralTypeIndex(pluralRules, pluralType, count) {
	  return pluralRules.pluralTypes[pluralType](count);
	}

	function createMemoizedPluralTypeNameSelector() {
	  var localePluralTypeStorage = {};

	  return function (pluralRules, locale) {
		var pluralType = localePluralTypeStorage[locale];

		if (pluralType && !pluralRules.pluralTypes[pluralType]) {
		  pluralType = null;
		  localePluralTypeStorage[locale] = pluralType;
		}

		if (!pluralType) {
		  pluralType = pluralTypeName(pluralRules, locale);

		  if (pluralType) {
			localePluralTypeStorage[locale] = pluralType;
		  }
		}

		return pluralType;
	  };
	}

	function escape(token) {
	  return token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
	}

	function constructTokenRegex(opts) {
	  var prefix = (opts && opts.prefix) || '%{';
	  var suffix = (opts && opts.suffix) || '}';

	  if (prefix === delimiter || suffix === delimiter) {
		throw new RangeError('"' + delimiter + '" token is reserved for pluralization');
	  }

	  return new RegExp(escape(prefix) + '(.*?)' + escape(suffix), 'g');
	}

	var memoizedPluralTypeName = createMemoizedPluralTypeNameSelector();

	var defaultTokenRegex = /%\{(.*?)\}/g;

	// ### transformPhrase(phrase, substitutions, locale)
	//
	// Takes a phrase string and transforms it by choosing the correct
	// plural form and interpolating it.
	//
	//     transformPhrase('Hello, %{name}!', {name: 'Spike'});
	//     // "Hello, Spike!"
	//
	// The correct plural form is selected if substitutions.smart_count
	// is set. You can pass in a number instead of an Object as `substitutions`
	// as a shortcut for `smart_count`.
	//
	//     transformPhrase('%{smart_count} new messages |||| 1 new message', {smart_count: 1}, 'en');
	//     // "1 new message"
	//
	//     transformPhrase('%{smart_count} new messages |||| 1 new message', {smart_count: 2}, 'en');
	//     // "2 new messages"
	//
	//     transformPhrase('%{smart_count} new messages |||| 1 new message', 5, 'en');
	//     // "5 new messages"
	//
	// You should pass in a third argument, the locale, to specify the correct plural type.
	// It defaults to `'en'` with 2 plural forms.
	function transformPhrase(
	  phrase,
	  substitutions,
	  locale,
	  tokenRegex,
	  pluralRules,
	  replaceImplementation
	) {
	  if (typeof phrase !== 'string') {
		throw new TypeError('Polyglot.transformPhrase expects argument #1 to be string');
	  }

	  if (substitutions == null) {
		return phrase;
	  }

	  var result = phrase;
	  var interpolationRegex = tokenRegex || defaultTokenRegex;
	  var replace = replaceImplementation || defaultReplace;

	  // allow number as a pluralization shortcut
	  var options = typeof substitutions === 'number' ? { smart_count: substitutions } : substitutions;

	  // Select plural form: based on a phrase text that contains `n`
	  // plural forms separated by `delimiter`, a `locale`, and a `substitutions.smart_count`,
	  // choose the correct plural form. This is only done if `count` is set.
	  if (options.smart_count != null && phrase) {
		var pluralRulesOrDefault = pluralRules || defaultPluralRules;
		var texts = split.call(phrase, delimiter);
		var bestLocale = locale || 'en';
		var pluralType = memoizedPluralTypeName(pluralRulesOrDefault, bestLocale);
		var pluralTypeWithCount = pluralTypeIndex(
		  pluralRulesOrDefault,
		  pluralType,
		  options.smart_count
		);

		result = defaultReplace.call(texts[pluralTypeWithCount] || texts[0], /^[^\S]*|[^\S]*$/g, '');
	  }

	  // Interpolate: Creates a `RegExp` object for each interpolation placeholder.
	  result = replace.call(result, interpolationRegex, function (expression, argument) {
		if (!has(options, argument) || options[argument] == null) { return expression; }
		return options[argument];
	  });

	  return result;
	}

	// ### Polyglot class constructor
	function Polyglot(options) {
	  var opts = options || {};
	  this.phrases = {};
	  this.extend(opts.phrases || {});
	  this.currentLocale = opts.locale || 'en';
	  var allowMissing = opts.allowMissing ? transformPhrase : null;
	  this.onMissingKey = typeof opts.onMissingKey === 'function' ? opts.onMissingKey : allowMissing;
	  this.warn = opts.warn || warn;
	  this.replaceImplementation = opts.replace || defaultReplace;
	  this.tokenRegex = constructTokenRegex(opts.interpolation);
	  this.pluralRules = opts.pluralRules || defaultPluralRules;
	}

	// ### polyglot.locale([locale])
	//
	// Get or set locale. Internally, Polyglot only uses locale for pluralization.
	Polyglot.prototype.locale = function (newLocale) {
	  if (newLocale) this.currentLocale = newLocale;
	  return this.currentLocale;
	};

	// ### polyglot.extend(phrases)
	//
	// Use `extend` to tell Polyglot how to translate a given key.
	//
	//     polyglot.extend({
	//       "hello": "Hello",
	//       "hello_name": "Hello, %{name}"
	//     });
	//
	// The key can be any string.  Feel free to call `extend` multiple times;
	// it will override any phrases with the same key, but leave existing phrases
	// untouched.
	//
	// It is also possible to pass nested phrase objects, which get flattened
	// into an object with the nested keys concatenated using dot notation.
	//
	//     polyglot.extend({
	//       "nav": {
	//         "hello": "Hello",
	//         "hello_name": "Hello, %{name}",
	//         "sidebar": {
	//           "welcome": "Welcome"
	//         }
	//       }
	//     });
	//
	//     console.log(polyglot.phrases);
	//     // {
	//     //   'nav.hello': 'Hello',
	//     //   'nav.hello_name': 'Hello, %{name}',
	//     //   'nav.sidebar.welcome': 'Welcome'
	//     // }
	//
	// `extend` accepts an optional second argument, `prefix`, which can be used
	// to prefix every key in the phrases object with some string, using dot
	// notation.
	//
	//     polyglot.extend({
	//       "hello": "Hello",
	//       "hello_name": "Hello, %{name}"
	//     }, "nav");
	//
	//     console.log(polyglot.phrases);
	//     // {
	//     //   'nav.hello': 'Hello',
	//     //   'nav.hello_name': 'Hello, %{name}'
	//     // }
	//
	// This feature is used internally to support nested phrase objects.
	Polyglot.prototype.extend = function (morePhrases, prefix) {
	  var phraseEntries = entries(morePhrases || {});
	  for (var i = 0; i < phraseEntries.length; i += 1) {
		var key = phraseEntries[i][0];
		var phrase = phraseEntries[i][1];
		var prefixedKey = prefix ? prefix + '.' + key : key;
		if (typeof phrase === 'object') {
		  this.extend(phrase, prefixedKey);
		} else {
		  this.phrases[prefixedKey] = phrase;
		}
	  }
	};

	// ### polyglot.unset(phrases)
	// Use `unset` to selectively remove keys from a polyglot instance.
	//
	//     polyglot.unset("some_key");
	//     polyglot.unset({
	//       "hello": "Hello",
	//       "hello_name": "Hello, %{name}"
	//     });
	//
	// The unset method can take either a string (for the key), or an object hash with
	// the keys that you would like to unset.
	Polyglot.prototype.unset = function (morePhrases, prefix) {
	  if (typeof morePhrases === 'string') {
		delete this.phrases[morePhrases];
	  } else {
		var phraseEntries = entries(morePhrases || {});
		for (var i = 0; i < phraseEntries.length; i += 1) {
		  var key = phraseEntries[i][0];
		  var phrase = phraseEntries[i][1];
		  var prefixedKey = prefix ? prefix + '.' + key : key;
		  if (typeof phrase === 'object') {
			this.unset(phrase, prefixedKey);
		  } else {
			delete this.phrases[prefixedKey];
		  }
		}
	  }
	};

	// ### polyglot.clear()
	//
	// Clears all phrases. Useful for special cases, such as freeing
	// up memory if you have lots of phrases but no longer need to
	// perform any translation. Also used internally by `replace`.
	Polyglot.prototype.clear = function () {
	  this.phrases = {};
	};

	// ### polyglot.replace(phrases)
	//
	// Completely replace the existing phrases with a new set of phrases.
	// Normally, just use `extend` to add more phrases, but under certain
	// circumstances, you may want to make sure no old phrases are lying around.
	Polyglot.prototype.replace = function (newPhrases) {
	  this.clear();
	  this.extend(newPhrases);
	};

	// ### polyglot.t(key, options)
	//
	// The most-used method. Provide a key, and `t` will return the
	// phrase.
	//
	//     polyglot.t("hello");
	//     => "Hello"
	//
	// The phrase value is provided first by a call to `polyglot.extend()` or
	// `polyglot.replace()`.
	//
	// Pass in an object as the second argument to perform interpolation.
	//
	//     polyglot.t("hello_name", {name: "Spike"});
	//     => "Hello, Spike"
	//
	// If you like, you can provide a default value in case the phrase is missing.
	// Use the special option key "_" to specify a default.
	//
	//     polyglot.t("i_like_to_write_in_language", {
	//       _: "I like to write in %{language}.",
	//       language: "JavaScript"
	//     });
	//     => "I like to write in JavaScript."
	//
	Polyglot.prototype.t = function (key, options) {
	  var phrase, result;
	  var opts = options == null ? {} : options;
	  if (typeof this.phrases[key] === 'string') {
		phrase = this.phrases[key];
	  } else if (typeof opts._ === 'string') {
		phrase = opts._;
	  } else if (this.onMissingKey) {
		var onMissingKey = this.onMissingKey;
		result = onMissingKey(
		  key,
		  opts,
		  this.currentLocale,
		  this.tokenRegex,
		  this.pluralRules,
		  this.replaceImplementation
		);
	  } else {
		this.warn('Missing translation for key: "' + key + '"');
		result = key;
	  }
	  if (typeof phrase === 'string') {
		result = transformPhrase(
		  phrase,
		  opts,
		  this.currentLocale,
		  this.tokenRegex,
		  this.pluralRules,
		  this.replaceImplementation
		);
	  }
	  return result;
	};

	// ### polyglot.has(key)
	//
	// Check if polyglot has a translation for given key
	Polyglot.prototype.has = function (key) {
	  return has(this.phrases, key);
	};

	// export transformPhrase
	Polyglot.transformPhrase = function transform(phrase, substitutions, locale) {
	  return transformPhrase(phrase, substitutions, locale);
	};

	module.exports = Polyglot;

	},{"hasown":35,"object.entries":48,"warning":52}],3:[function(require,module,exports){
	'use strict';

	var bind = require('function-bind');

	var $apply = require('./functionApply');
	var $call = require('./functionCall');
	var $reflectApply = require('./reflectApply');

	/** @type {import('./actualApply')} */
	module.exports = $reflectApply || bind.call($call, $apply);

	},{"./functionApply":5,"./functionCall":6,"./reflectApply":8,"function-bind":25}],4:[function(require,module,exports){
	'use strict';

	var bind = require('function-bind');
	var $apply = require('./functionApply');
	var actualApply = require('./actualApply');

	/** @type {import('./applyBind')} */
	module.exports = function applyBind() {
		return actualApply(bind, $apply, arguments);
	};

	},{"./actualApply":3,"./functionApply":5,"function-bind":25}],5:[function(require,module,exports){
	'use strict';

	/** @type {import('./functionApply')} */
	module.exports = Function.prototype.apply;

	},{}],6:[function(require,module,exports){
	'use strict';

	/** @type {import('./functionCall')} */
	module.exports = Function.prototype.call;

	},{}],7:[function(require,module,exports){
	'use strict';

	var bind = require('function-bind');
	var $TypeError = require('es-errors/type');

	var $call = require('./functionCall');
	var $actualApply = require('./actualApply');

	/** @type {(args: [Function, thisArg?: unknown, ...args: unknown[]]) => Function} TODO FIXME, find a way to use import('.') */
	module.exports = function callBindBasic(args) {
		if (args.length < 1 || typeof args[0] !== 'function') {
			throw new $TypeError('a function is required');
		}
		return $actualApply(bind, $call, args);
	};

	},{"./actualApply":3,"./functionCall":6,"es-errors/type":20,"function-bind":25}],8:[function(require,module,exports){
	'use strict';

	/** @type {import('./reflectApply')} */
	module.exports = typeof Reflect !== 'undefined' && Reflect && Reflect.apply;

	},{}],9:[function(require,module,exports){
	'use strict';

	var setFunctionLength = require('set-function-length');

	var $defineProperty = require('es-define-property');

	var callBindBasic = require('call-bind-apply-helpers');
	var applyBind = require('call-bind-apply-helpers/applyBind');

	module.exports = function callBind(originalFunction) {
		var func = callBindBasic(arguments);
		var adjustedLength = originalFunction.length - (arguments.length - 1);
		return setFunctionLength(
			func,
			1 + (adjustedLength > 0 ? adjustedLength : 0),
			true
		);
	};

	if ($defineProperty) {
		$defineProperty(module.exports, 'apply', { value: applyBind });
	} else {
		module.exports.apply = applyBind;
	}

	},{"call-bind-apply-helpers":7,"call-bind-apply-helpers/applyBind":4,"es-define-property":14,"set-function-length":51}],10:[function(require,module,exports){
	'use strict';

	var GetIntrinsic = require('get-intrinsic');

	var callBindBasic = require('call-bind-apply-helpers');

	/** @type {(thisArg: string, searchString: string, position?: number) => number} */
	var $indexOf = callBindBasic([GetIntrinsic('%String.prototype.indexOf%')]);

	/** @type {import('.')} */
	module.exports = function callBoundIntrinsic(name, allowMissing) {
		/* eslint no-extra-parens: 0 */

		var intrinsic = /** @type {(this: unknown, ...args: unknown[]) => unknown} */ (GetIntrinsic(name, !!allowMissing));
		if (typeof intrinsic === 'function' && $indexOf(name, '.prototype.') > -1) {
			return callBindBasic(/** @type {const} */ ([intrinsic]));
		}
		return intrinsic;
	};

	},{"call-bind-apply-helpers":7,"get-intrinsic":26}],11:[function(require,module,exports){
	'use strict';

	var $defineProperty = require('es-define-property');

	var $SyntaxError = require('es-errors/syntax');
	var $TypeError = require('es-errors/type');

	var gopd = require('gopd');

	/** @type {import('.')} */
	module.exports = function defineDataProperty(
		obj,
		property,
		value
	) {
		if (!obj || (typeof obj !== 'object' && typeof obj !== 'function')) {
			throw new $TypeError('`obj` must be an object or a function`');
		}
		if (typeof property !== 'string' && typeof property !== 'symbol') {
			throw new $TypeError('`property` must be a string or a symbol`');
		}
		if (arguments.length > 3 && typeof arguments[3] !== 'boolean' && arguments[3] !== null) {
			throw new $TypeError('`nonEnumerable`, if provided, must be a boolean or null');
		}
		if (arguments.length > 4 && typeof arguments[4] !== 'boolean' && arguments[4] !== null) {
			throw new $TypeError('`nonWritable`, if provided, must be a boolean or null');
		}
		if (arguments.length > 5 && typeof arguments[5] !== 'boolean' && arguments[5] !== null) {
			throw new $TypeError('`nonConfigurable`, if provided, must be a boolean or null');
		}
		if (arguments.length > 6 && typeof arguments[6] !== 'boolean') {
			throw new $TypeError('`loose`, if provided, must be a boolean');
		}

		var nonEnumerable = arguments.length > 3 ? arguments[3] : null;
		var nonWritable = arguments.length > 4 ? arguments[4] : null;
		var nonConfigurable = arguments.length > 5 ? arguments[5] : null;
		var loose = arguments.length > 6 ? arguments[6] : false;

		/* @type {false | TypedPropertyDescriptor<unknown>} */
		var desc = !!gopd && gopd(obj, property);

		if ($defineProperty) {
			$defineProperty(obj, property, {
				configurable: nonConfigurable === null && desc ? desc.configurable : !nonConfigurable,
				enumerable: nonEnumerable === null && desc ? desc.enumerable : !nonEnumerable,
				value: value,
				writable: nonWritable === null && desc ? desc.writable : !nonWritable
			});
		} else if (loose || (!nonEnumerable && !nonWritable && !nonConfigurable)) {
			// must fall back to [[Set]], and was not explicitly asked to make non-enumerable, non-writable, or non-configurable
			obj[property] = value; // eslint-disable-line no-param-reassign
		} else {
			throw new $SyntaxError('This environment does not support defining a property as non-configurable, non-writable, or non-enumerable.');
		}
	};

	},{"es-define-property":14,"es-errors/syntax":19,"es-errors/type":20,"gopd":31}],12:[function(require,module,exports){
	'use strict';

	var keys = require('object-keys');
	var hasSymbols = typeof Symbol === 'function' && typeof Symbol('foo') === 'symbol';

	var toStr = Object.prototype.toString;
	var concat = Array.prototype.concat;
	var defineDataProperty = require('define-data-property');

	var isFunction = function (fn) {
		return typeof fn === 'function' && toStr.call(fn) === '[object Function]';
	};

	var supportsDescriptors = require('has-property-descriptors')();

	var defineProperty = function (object, name, value, predicate) {
		if (name in object) {
			if (predicate === true) {
				if (object[name] === value) {
					return;
				}
			} else if (!isFunction(predicate) || !predicate()) {
				return;
			}
		}

		if (supportsDescriptors) {
			defineDataProperty(object, name, value, true);
		} else {
			defineDataProperty(object, name, value);
		}
	};

	var defineProperties = function (object, map) {
		var predicates = arguments.length > 2 ? arguments[2] : {};
		var props = keys(map);
		if (hasSymbols) {
			props = concat.call(props, Object.getOwnPropertySymbols(map));
		}
		for (var i = 0; i < props.length; i += 1) {
			defineProperty(object, props[i], map[props[i]], predicates[props[i]]);
		}
	};

	defineProperties.supportsDescriptors = !!supportsDescriptors;

	module.exports = defineProperties;

	},{"define-data-property":11,"has-property-descriptors":32,"object-keys":45}],13:[function(require,module,exports){
	'use strict';

	var callBind = require('call-bind-apply-helpers');
	var gOPD = require('gopd');

	var hasProtoAccessor;
	try {
		// eslint-disable-next-line no-extra-parens, no-proto
		hasProtoAccessor = /** @type {{ __proto__?: typeof Array.prototype }} */ ([]).__proto__ === Array.prototype;
	} catch (e) {
		if (!e || typeof e !== 'object' || !('code' in e) || e.code !== 'ERR_PROTO_ACCESS') {
			throw e;
		}
	}

	// eslint-disable-next-line no-extra-parens
	var desc = !!hasProtoAccessor && gOPD && gOPD(Object.prototype, /** @type {keyof typeof Object.prototype} */ ('__proto__'));

	var $Object = Object;
	var $getPrototypeOf = $Object.getPrototypeOf;

	/** @type {import('./get')} */
	module.exports = desc && typeof desc.get === 'function'
		? callBind([desc.get])
		: typeof $getPrototypeOf === 'function'
			? /** @type {import('./get')} */ function getDunder(value) {
				// eslint-disable-next-line eqeqeq
				return $getPrototypeOf(value == null ? value : $Object(value));
			}
			: false;

	},{"call-bind-apply-helpers":7,"gopd":31}],14:[function(require,module,exports){
	'use strict';

	/** @type {import('.')} */
	var $defineProperty = Object.defineProperty || false;
	if ($defineProperty) {
		try {
			$defineProperty({}, 'a', { value: 1 });
		} catch (e) {
			// IE 8 has a broken defineProperty
			$defineProperty = false;
		}
	}

	module.exports = $defineProperty;

	},{}],15:[function(require,module,exports){
	'use strict';

	/** @type {import('./eval')} */
	module.exports = EvalError;

	},{}],16:[function(require,module,exports){
	'use strict';

	/** @type {import('.')} */
	module.exports = Error;

	},{}],17:[function(require,module,exports){
	'use strict';

	/** @type {import('./range')} */
	module.exports = RangeError;

	},{}],18:[function(require,module,exports){
	'use strict';

	/** @type {import('./ref')} */
	module.exports = ReferenceError;

	},{}],19:[function(require,module,exports){
	'use strict';

	/** @type {import('./syntax')} */
	module.exports = SyntaxError;

	},{}],20:[function(require,module,exports){
	'use strict';

	/** @type {import('./type')} */
	module.exports = TypeError;

	},{}],21:[function(require,module,exports){
	'use strict';

	/** @type {import('./uri')} */
	module.exports = URIError;

	},{}],22:[function(require,module,exports){
	'use strict';

	var $TypeError = require('es-errors/type');

	/** @type {import('./RequireObjectCoercible')} */
	module.exports = function RequireObjectCoercible(value) {
		if (value == null) {
			throw new $TypeError((arguments.length > 0 && arguments[1]) || ('Cannot call method on ' + value));
		}
		return value;
	};

	},{"es-errors/type":20}],23:[function(require,module,exports){
	'use strict';

	/** @type {import('.')} */
	module.exports = Object;

	},{}],24:[function(require,module,exports){
	'use strict';

	/* eslint no-invalid-this: 1 */

	var ERROR_MESSAGE = 'Function.prototype.bind called on incompatible ';
	var toStr = Object.prototype.toString;
	var max = Math.max;
	var funcType = '[object Function]';

	var concatty = function concatty(a, b) {
		var arr = [];

		for (var i = 0; i < a.length; i += 1) {
			arr[i] = a[i];
		}
		for (var j = 0; j < b.length; j += 1) {
			arr[j + a.length] = b[j];
		}

		return arr;
	};

	var slicy = function slicy(arrLike, offset) {
		var arr = [];
		for (var i = offset || 0, j = 0; i < arrLike.length; i += 1, j += 1) {
			arr[j] = arrLike[i];
		}
		return arr;
	};

	var joiny = function (arr, joiner) {
		var str = '';
		for (var i = 0; i < arr.length; i += 1) {
			str += arr[i];
			if (i + 1 < arr.length) {
				str += joiner;
			}
		}
		return str;
	};

	module.exports = function bind(that) {
		var target = this;
		if (typeof target !== 'function' || toStr.apply(target) !== funcType) {
			throw new TypeError(ERROR_MESSAGE + target);
		}
		var args = slicy(arguments, 1);

		var bound;
		var binder = function () {
			if (this instanceof bound) {
				var result = target.apply(
					this,
					concatty(args, arguments)
				);
				if (Object(result) === result) {
					return result;
				}
				return this;
			}
			return target.apply(
				that,
				concatty(args, arguments)
			);

		};

		var boundLength = max(0, target.length - args.length);
		var boundArgs = [];
		for (var i = 0; i < boundLength; i++) {
			boundArgs[i] = '$' + i;
		}

		bound = Function('binder', 'return function (' + joiny(boundArgs, ',') + '){ return binder.apply(this,arguments); }')(binder);

		if (target.prototype) {
			var Empty = function Empty() {};
			Empty.prototype = target.prototype;
			bound.prototype = new Empty();
			Empty.prototype = null;
		}

		return bound;
	};

	},{}],25:[function(require,module,exports){
	'use strict';

	var implementation = require('./implementation');

	module.exports = Function.prototype.bind || implementation;

	},{"./implementation":24}],26:[function(require,module,exports){
	'use strict';

	var undefined;

	var $Object = require('es-object-atoms');

	var $Error = require('es-errors');
	var $EvalError = require('es-errors/eval');
	var $RangeError = require('es-errors/range');
	var $ReferenceError = require('es-errors/ref');
	var $SyntaxError = require('es-errors/syntax');
	var $TypeError = require('es-errors/type');
	var $URIError = require('es-errors/uri');

	var abs = require('math-intrinsics/abs');
	var floor = require('math-intrinsics/floor');
	var max = require('math-intrinsics/max');
	var min = require('math-intrinsics/min');
	var pow = require('math-intrinsics/pow');
	var round = require('math-intrinsics/round');
	var sign = require('math-intrinsics/sign');

	var $Function = Function;

	// eslint-disable-next-line consistent-return
	var getEvalledConstructor = function (expressionSyntax) {
		try {
			return $Function('"use strict"; return (' + expressionSyntax + ').constructor;')();
		} catch (e) {}
	};

	var $gOPD = require('gopd');
	var $defineProperty = require('es-define-property');

	var throwTypeError = function () {
		throw new $TypeError();
	};
	var ThrowTypeError = $gOPD
		? (function () {
			try {
				// eslint-disable-next-line no-unused-expressions, no-caller, no-restricted-properties
				arguments.callee; // IE 8 does not throw here
				return throwTypeError;
			} catch (calleeThrows) {
				try {
					// IE 8 throws on Object.getOwnPropertyDescriptor(arguments, '')
					return $gOPD(arguments, 'callee').get;
				} catch (gOPDthrows) {
					return throwTypeError;
				}
			}
		}())
		: throwTypeError;

	var hasSymbols = require('has-symbols')();

	var getProto = require('get-proto');
	var $ObjectGPO = require('get-proto/Object.getPrototypeOf');
	var $ReflectGPO = require('get-proto/Reflect.getPrototypeOf');

	var $apply = require('call-bind-apply-helpers/functionApply');
	var $call = require('call-bind-apply-helpers/functionCall');

	var needsEval = {};

	var TypedArray = typeof Uint8Array === 'undefined' || !getProto ? undefined : getProto(Uint8Array);

	var INTRINSICS = {
		__proto__: null,
		'%AggregateError%': typeof AggregateError === 'undefined' ? undefined : AggregateError,
		'%Array%': Array,
		'%ArrayBuffer%': typeof ArrayBuffer === 'undefined' ? undefined : ArrayBuffer,
		'%ArrayIteratorPrototype%': hasSymbols && getProto ? getProto([][Symbol.iterator]()) : undefined,
		'%AsyncFromSyncIteratorPrototype%': undefined,
		'%AsyncFunction%': needsEval,
		'%AsyncGenerator%': needsEval,
		'%AsyncGeneratorFunction%': needsEval,
		'%AsyncIteratorPrototype%': needsEval,
		'%Atomics%': typeof Atomics === 'undefined' ? undefined : Atomics,
		'%BigInt%': typeof BigInt === 'undefined' ? undefined : BigInt,
		'%BigInt64Array%': typeof BigInt64Array === 'undefined' ? undefined : BigInt64Array,
		'%BigUint64Array%': typeof BigUint64Array === 'undefined' ? undefined : BigUint64Array,
		'%Boolean%': Boolean,
		'%DataView%': typeof DataView === 'undefined' ? undefined : DataView,
		'%Date%': Date,
		'%decodeURI%': decodeURI,
		'%decodeURIComponent%': decodeURIComponent,
		'%encodeURI%': encodeURI,
		'%encodeURIComponent%': encodeURIComponent,
		'%Error%': $Error,
		'%eval%': eval, // eslint-disable-line no-eval
		'%EvalError%': $EvalError,
		'%Float16Array%': typeof Float16Array === 'undefined' ? undefined : Float16Array,
		'%Float32Array%': typeof Float32Array === 'undefined' ? undefined : Float32Array,
		'%Float64Array%': typeof Float64Array === 'undefined' ? undefined : Float64Array,
		'%FinalizationRegistry%': typeof FinalizationRegistry === 'undefined' ? undefined : FinalizationRegistry,
		'%Function%': $Function,
		'%GeneratorFunction%': needsEval,
		'%Int8Array%': typeof Int8Array === 'undefined' ? undefined : Int8Array,
		'%Int16Array%': typeof Int16Array === 'undefined' ? undefined : Int16Array,
		'%Int32Array%': typeof Int32Array === 'undefined' ? undefined : Int32Array,
		'%isFinite%': isFinite,
		'%isNaN%': isNaN,
		'%IteratorPrototype%': hasSymbols && getProto ? getProto(getProto([][Symbol.iterator]())) : undefined,
		'%JSON%': typeof JSON === 'object' ? JSON : undefined,
		'%Map%': typeof Map === 'undefined' ? undefined : Map,
		'%MapIteratorPrototype%': typeof Map === 'undefined' || !hasSymbols || !getProto ? undefined : getProto(new Map()[Symbol.iterator]()),
		'%Math%': Math,
		'%Number%': Number,
		'%Object%': $Object,
		'%Object.getOwnPropertyDescriptor%': $gOPD,
		'%parseFloat%': parseFloat,
		'%parseInt%': parseInt,
		'%Promise%': typeof Promise === 'undefined' ? undefined : Promise,
		'%Proxy%': typeof Proxy === 'undefined' ? undefined : Proxy,
		'%RangeError%': $RangeError,
		'%ReferenceError%': $ReferenceError,
		'%Reflect%': typeof Reflect === 'undefined' ? undefined : Reflect,
		'%RegExp%': RegExp,
		'%Set%': typeof Set === 'undefined' ? undefined : Set,
		'%SetIteratorPrototype%': typeof Set === 'undefined' || !hasSymbols || !getProto ? undefined : getProto(new Set()[Symbol.iterator]()),
		'%SharedArrayBuffer%': typeof SharedArrayBuffer === 'undefined' ? undefined : SharedArrayBuffer,
		'%String%': String,
		'%StringIteratorPrototype%': hasSymbols && getProto ? getProto(''[Symbol.iterator]()) : undefined,
		'%Symbol%': hasSymbols ? Symbol : undefined,
		'%SyntaxError%': $SyntaxError,
		'%ThrowTypeError%': ThrowTypeError,
		'%TypedArray%': TypedArray,
		'%TypeError%': $TypeError,
		'%Uint8Array%': typeof Uint8Array === 'undefined' ? undefined : Uint8Array,
		'%Uint8ClampedArray%': typeof Uint8ClampedArray === 'undefined' ? undefined : Uint8ClampedArray,
		'%Uint16Array%': typeof Uint16Array === 'undefined' ? undefined : Uint16Array,
		'%Uint32Array%': typeof Uint32Array === 'undefined' ? undefined : Uint32Array,
		'%URIError%': $URIError,
		'%WeakMap%': typeof WeakMap === 'undefined' ? undefined : WeakMap,
		'%WeakRef%': typeof WeakRef === 'undefined' ? undefined : WeakRef,
		'%WeakSet%': typeof WeakSet === 'undefined' ? undefined : WeakSet,

		'%Function.prototype.call%': $call,
		'%Function.prototype.apply%': $apply,
		'%Object.defineProperty%': $defineProperty,
		'%Object.getPrototypeOf%': $ObjectGPO,
		'%Math.abs%': abs,
		'%Math.floor%': floor,
		'%Math.max%': max,
		'%Math.min%': min,
		'%Math.pow%': pow,
		'%Math.round%': round,
		'%Math.sign%': sign,
		'%Reflect.getPrototypeOf%': $ReflectGPO
	};

	if (getProto) {
		try {
			null.error; // eslint-disable-line no-unused-expressions
		} catch (e) {
			// https://github.com/tc39/proposal-shadowrealm/pull/384#issuecomment-1364264229
			var errorProto = getProto(getProto(e));
			INTRINSICS['%Error.prototype%'] = errorProto;
		}
	}

	var doEval = function doEval(name) {
		var value;
		if (name === '%AsyncFunction%') {
			value = getEvalledConstructor('async function () {}');
		} else if (name === '%GeneratorFunction%') {
			value = getEvalledConstructor('function* () {}');
		} else if (name === '%AsyncGeneratorFunction%') {
			value = getEvalledConstructor('async function* () {}');
		} else if (name === '%AsyncGenerator%') {
			var fn = doEval('%AsyncGeneratorFunction%');
			if (fn) {
				value = fn.prototype;
			}
		} else if (name === '%AsyncIteratorPrototype%') {
			var gen = doEval('%AsyncGenerator%');
			if (gen && getProto) {
				value = getProto(gen.prototype);
			}
		}

		INTRINSICS[name] = value;

		return value;
	};

	var LEGACY_ALIASES = {
		__proto__: null,
		'%ArrayBufferPrototype%': ['ArrayBuffer', 'prototype'],
		'%ArrayPrototype%': ['Array', 'prototype'],
		'%ArrayProto_entries%': ['Array', 'prototype', 'entries'],
		'%ArrayProto_forEach%': ['Array', 'prototype', 'forEach'],
		'%ArrayProto_keys%': ['Array', 'prototype', 'keys'],
		'%ArrayProto_values%': ['Array', 'prototype', 'values'],
		'%AsyncFunctionPrototype%': ['AsyncFunction', 'prototype'],
		'%AsyncGenerator%': ['AsyncGeneratorFunction', 'prototype'],
		'%AsyncGeneratorPrototype%': ['AsyncGeneratorFunction', 'prototype', 'prototype'],
		'%BooleanPrototype%': ['Boolean', 'prototype'],
		'%DataViewPrototype%': ['DataView', 'prototype'],
		'%DatePrototype%': ['Date', 'prototype'],
		'%ErrorPrototype%': ['Error', 'prototype'],
		'%EvalErrorPrototype%': ['EvalError', 'prototype'],
		'%Float32ArrayPrototype%': ['Float32Array', 'prototype'],
		'%Float64ArrayPrototype%': ['Float64Array', 'prototype'],
		'%FunctionPrototype%': ['Function', 'prototype'],
		'%Generator%': ['GeneratorFunction', 'prototype'],
		'%GeneratorPrototype%': ['GeneratorFunction', 'prototype', 'prototype'],
		'%Int8ArrayPrototype%': ['Int8Array', 'prototype'],
		'%Int16ArrayPrototype%': ['Int16Array', 'prototype'],
		'%Int32ArrayPrototype%': ['Int32Array', 'prototype'],
		'%JSONParse%': ['JSON', 'parse'],
		'%JSONStringify%': ['JSON', 'stringify'],
		'%MapPrototype%': ['Map', 'prototype'],
		'%NumberPrototype%': ['Number', 'prototype'],
		'%ObjectPrototype%': ['Object', 'prototype'],
		'%ObjProto_toString%': ['Object', 'prototype', 'toString'],
		'%ObjProto_valueOf%': ['Object', 'prototype', 'valueOf'],
		'%PromisePrototype%': ['Promise', 'prototype'],
		'%PromiseProto_then%': ['Promise', 'prototype', 'then'],
		'%Promise_all%': ['Promise', 'all'],
		'%Promise_reject%': ['Promise', 'reject'],
		'%Promise_resolve%': ['Promise', 'resolve'],
		'%RangeErrorPrototype%': ['RangeError', 'prototype'],
		'%ReferenceErrorPrototype%': ['ReferenceError', 'prototype'],
		'%RegExpPrototype%': ['RegExp', 'prototype'],
		'%SetPrototype%': ['Set', 'prototype'],
		'%SharedArrayBufferPrototype%': ['SharedArrayBuffer', 'prototype'],
		'%StringPrototype%': ['String', 'prototype'],
		'%SymbolPrototype%': ['Symbol', 'prototype'],
		'%SyntaxErrorPrototype%': ['SyntaxError', 'prototype'],
		'%TypedArrayPrototype%': ['TypedArray', 'prototype'],
		'%TypeErrorPrototype%': ['TypeError', 'prototype'],
		'%Uint8ArrayPrototype%': ['Uint8Array', 'prototype'],
		'%Uint8ClampedArrayPrototype%': ['Uint8ClampedArray', 'prototype'],
		'%Uint16ArrayPrototype%': ['Uint16Array', 'prototype'],
		'%Uint32ArrayPrototype%': ['Uint32Array', 'prototype'],
		'%URIErrorPrototype%': ['URIError', 'prototype'],
		'%WeakMapPrototype%': ['WeakMap', 'prototype'],
		'%WeakSetPrototype%': ['WeakSet', 'prototype']
	};

	var bind = require('function-bind');
	var hasOwn = require('hasown');
	var $concat = bind.call($call, Array.prototype.concat);
	var $spliceApply = bind.call($apply, Array.prototype.splice);
	var $replace = bind.call($call, String.prototype.replace);
	var $strSlice = bind.call($call, String.prototype.slice);
	var $exec = bind.call($call, RegExp.prototype.exec);

	/* adapted from https://github.com/lodash/lodash/blob/4.17.15/dist/lodash.js#L6735-L6744 */
	var rePropName = /[^%.[\]]+|\[(?:(-?\d+(?:\.\d+)?)|(["'])((?:(?!\2)[^\\]|\\.)*?)\2)\]|(?=(?:\.|\[\])(?:\.|\[\]|%$))/g;
	var reEscapeChar = /\\(\\)?/g; /** Used to match backslashes in property paths. */
	var stringToPath = function stringToPath(string) {
		var first = $strSlice(string, 0, 1);
		var last = $strSlice(string, -1);
		if (first === '%' && last !== '%') {
			throw new $SyntaxError('invalid intrinsic syntax, expected closing `%`');
		} else if (last === '%' && first !== '%') {
			throw new $SyntaxError('invalid intrinsic syntax, expected opening `%`');
		}
		var result = [];
		$replace(string, rePropName, function (match, number, quote, subString) {
			result[result.length] = quote ? $replace(subString, reEscapeChar, '$1') : number || match;
		});
		return result;
	};
	/* end adaptation */

	var getBaseIntrinsic = function getBaseIntrinsic(name, allowMissing) {
		var intrinsicName = name;
		var alias;
		if (hasOwn(LEGACY_ALIASES, intrinsicName)) {
			alias = LEGACY_ALIASES[intrinsicName];
			intrinsicName = '%' + alias[0] + '%';
		}

		if (hasOwn(INTRINSICS, intrinsicName)) {
			var value = INTRINSICS[intrinsicName];
			if (value === needsEval) {
				value = doEval(intrinsicName);
			}
			if (typeof value === 'undefined' && !allowMissing) {
				throw new $TypeError('intrinsic ' + name + ' exists, but is not available. Please file an issue!');
			}

			return {
				alias: alias,
				name: intrinsicName,
				value: value
			};
		}

		throw new $SyntaxError('intrinsic ' + name + ' does not exist!');
	};

	module.exports = function GetIntrinsic(name, allowMissing) {
		if (typeof name !== 'string' || name.length === 0) {
			throw new $TypeError('intrinsic name must be a non-empty string');
		}
		if (arguments.length > 1 && typeof allowMissing !== 'boolean') {
			throw new $TypeError('"allowMissing" argument must be a boolean');
		}

		if ($exec(/^%?[^%]*%?$/, name) === null) {
			throw new $SyntaxError('`%` may not be present anywhere but at the beginning and end of the intrinsic name');
		}
		var parts = stringToPath(name);
		var intrinsicBaseName = parts.length > 0 ? parts[0] : '';

		var intrinsic = getBaseIntrinsic('%' + intrinsicBaseName + '%', allowMissing);
		var intrinsicRealName = intrinsic.name;
		var value = intrinsic.value;
		var skipFurtherCaching = false;

		var alias = intrinsic.alias;
		if (alias) {
			intrinsicBaseName = alias[0];
			$spliceApply(parts, $concat([0, 1], alias));
		}

		for (var i = 1, isOwn = true; i < parts.length; i += 1) {
			var part = parts[i];
			var first = $strSlice(part, 0, 1);
			var last = $strSlice(part, -1);
			if (
				(
					(first === '"' || first === "'" || first === '`')
					|| (last === '"' || last === "'" || last === '`')
				)
				&& first !== last
			) {
				throw new $SyntaxError('property names with quotes must have matching quotes');
			}
			if (part === 'constructor' || !isOwn) {
				skipFurtherCaching = true;
			}

			intrinsicBaseName += '.' + part;
			intrinsicRealName = '%' + intrinsicBaseName + '%';

			if (hasOwn(INTRINSICS, intrinsicRealName)) {
				value = INTRINSICS[intrinsicRealName];
			} else if (value != null) {
				if (!(part in value)) {
					if (!allowMissing) {
						throw new $TypeError('base intrinsic for ' + name + ' exists, but the property is not available.');
					}
					return void undefined;
				}
				if ($gOPD && (i + 1) >= parts.length) {
					var desc = $gOPD(value, part);
					isOwn = !!desc;

					// By convention, when a data property is converted to an accessor
					// property to emulate a data property that does not suffer from
					// the override mistake, that accessor's getter is marked with
					// an `originalValue` property. Here, when we detect this, we
					// uphold the illusion by pretending to see that original data
					// property, i.e., returning the value rather than the getter
					// itself.
					if (isOwn && 'get' in desc && !('originalValue' in desc.get)) {
						value = desc.get;
					} else {
						value = value[part];
					}
				} else {
					isOwn = hasOwn(value, part);
					value = value[part];
				}

				if (isOwn && !skipFurtherCaching) {
					INTRINSICS[intrinsicRealName] = value;
				}
			}
		}
		return value;
	};

	},{"call-bind-apply-helpers/functionApply":5,"call-bind-apply-helpers/functionCall":6,"es-define-property":14,"es-errors":16,"es-errors/eval":15,"es-errors/range":17,"es-errors/ref":18,"es-errors/syntax":19,"es-errors/type":20,"es-errors/uri":21,"es-object-atoms":23,"function-bind":25,"get-proto":29,"get-proto/Object.getPrototypeOf":27,"get-proto/Reflect.getPrototypeOf":28,"gopd":31,"has-symbols":33,"hasown":35,"math-intrinsics/abs":36,"math-intrinsics/floor":37,"math-intrinsics/max":39,"math-intrinsics/min":40,"math-intrinsics/pow":41,"math-intrinsics/round":42,"math-intrinsics/sign":43}],27:[function(require,module,exports){
	'use strict';

	var $Object = require('es-object-atoms');

	/** @type {import('./Object.getPrototypeOf')} */
	module.exports = $Object.getPrototypeOf || null;

	},{"es-object-atoms":23}],28:[function(require,module,exports){
	'use strict';

	/** @type {import('./Reflect.getPrototypeOf')} */
	module.exports = (typeof Reflect !== 'undefined' && Reflect.getPrototypeOf) || null;

	},{}],29:[function(require,module,exports){
	'use strict';

	var reflectGetProto = require('./Reflect.getPrototypeOf');
	var originalGetProto = require('./Object.getPrototypeOf');

	var getDunderProto = require('dunder-proto/get');

	/** @type {import('.')} */
	module.exports = reflectGetProto
		? function getProto(O) {
			// @ts-expect-error TS can't narrow inside a closure, for some reason
			return reflectGetProto(O);
		}
		: originalGetProto
			? function getProto(O) {
				if (!O || (typeof O !== 'object' && typeof O !== 'function')) {
					throw new TypeError('getProto: not an object');
				}
				// @ts-expect-error TS can't narrow inside a closure, for some reason
				return originalGetProto(O);
			}
			: getDunderProto
				? function getProto(O) {
					// @ts-expect-error TS can't narrow inside a closure, for some reason
					return getDunderProto(O);
				}
				: null;

	},{"./Object.getPrototypeOf":27,"./Reflect.getPrototypeOf":28,"dunder-proto/get":13}],30:[function(require,module,exports){
	'use strict';

	/** @type {import('./gOPD')} */
	module.exports = Object.getOwnPropertyDescriptor;

	},{}],31:[function(require,module,exports){
	'use strict';

	/** @type {import('.')} */
	var $gOPD = require('./gOPD');

	if ($gOPD) {
		try {
			$gOPD([], 'length');
		} catch (e) {
			// IE 8 has a broken gOPD
			$gOPD = null;
		}
	}

	module.exports = $gOPD;

	},{"./gOPD":30}],32:[function(require,module,exports){
	'use strict';

	var $defineProperty = require('es-define-property');

	var hasPropertyDescriptors = function hasPropertyDescriptors() {
		return !!$defineProperty;
	};

	hasPropertyDescriptors.hasArrayLengthDefineBug = function hasArrayLengthDefineBug() {
		// node v0.6 has a bug where array lengths can be Set but not Defined
		if (!$defineProperty) {
			return null;
		}
		try {
			return $defineProperty([], 'length', { value: 1 }).length !== 1;
		} catch (e) {
			// In Firefox 4-22, defining length on an array throws an exception.
			return true;
		}
	};

	module.exports = hasPropertyDescriptors;

	},{"es-define-property":14}],33:[function(require,module,exports){
	'use strict';

	var origSymbol = typeof Symbol !== 'undefined' && Symbol;
	var hasSymbolSham = require('./shams');

	/** @type {import('.')} */
	module.exports = function hasNativeSymbols() {
		if (typeof origSymbol !== 'function') { return false; }
		if (typeof Symbol !== 'function') { return false; }
		if (typeof origSymbol('foo') !== 'symbol') { return false; }
		if (typeof Symbol('bar') !== 'symbol') { return false; }

		return hasSymbolSham();
	};

	},{"./shams":34}],34:[function(require,module,exports){
	'use strict';

	/** @type {import('./shams')} */
	/* eslint complexity: [2, 18], max-statements: [2, 33] */
	module.exports = function hasSymbols() {
		if (typeof Symbol !== 'function' || typeof Object.getOwnPropertySymbols !== 'function') { return false; }
		if (typeof Symbol.iterator === 'symbol') { return true; }

		/** @type {{ [k in symbol]?: unknown }} */
		var obj = {};
		var sym = Symbol('test');
		var symObj = Object(sym);
		if (typeof sym === 'string') { return false; }

		if (Object.prototype.toString.call(sym) !== '[object Symbol]') { return false; }
		if (Object.prototype.toString.call(symObj) !== '[object Symbol]') { return false; }

		// temp disabled per https://github.com/ljharb/object.assign/issues/17
		// if (sym instanceof Symbol) { return false; }
		// temp disabled per https://github.com/WebReflection/get-own-property-symbols/issues/4
		// if (!(symObj instanceof Symbol)) { return false; }

		// if (typeof Symbol.prototype.toString !== 'function') { return false; }
		// if (String(sym) !== Symbol.prototype.toString.call(sym)) { return false; }

		var symVal = 42;
		obj[sym] = symVal;
		for (var _ in obj) { return false; } // eslint-disable-line no-restricted-syntax, no-unreachable-loop
		if (typeof Object.keys === 'function' && Object.keys(obj).length !== 0) { return false; }

		if (typeof Object.getOwnPropertyNames === 'function' && Object.getOwnPropertyNames(obj).length !== 0) { return false; }

		var syms = Object.getOwnPropertySymbols(obj);
		if (syms.length !== 1 || syms[0] !== sym) { return false; }

		if (!Object.prototype.propertyIsEnumerable.call(obj, sym)) { return false; }

		if (typeof Object.getOwnPropertyDescriptor === 'function') {
			// eslint-disable-next-line no-extra-parens
			var descriptor = /** @type {PropertyDescriptor} */ (Object.getOwnPropertyDescriptor(obj, sym));
			if (descriptor.value !== symVal || descriptor.enumerable !== true) { return false; }
		}

		return true;
	};

	},{}],35:[function(require,module,exports){
	'use strict';

	var call = Function.prototype.call;
	var $hasOwn = Object.prototype.hasOwnProperty;
	var bind = require('function-bind');

	/** @type {import('.')} */
	module.exports = bind.call(call, $hasOwn);

	},{"function-bind":25}],36:[function(require,module,exports){
	'use strict';

	/** @type {import('./abs')} */
	module.exports = Math.abs;

	},{}],37:[function(require,module,exports){
	'use strict';

	/** @type {import('./floor')} */
	module.exports = Math.floor;

	},{}],38:[function(require,module,exports){
	'use strict';

	/** @type {import('./isNaN')} */
	module.exports = Number.isNaN || function isNaN(a) {
		return a !== a;
	};

	},{}],39:[function(require,module,exports){
	'use strict';

	/** @type {import('./max')} */
	module.exports = Math.max;

	},{}],40:[function(require,module,exports){
	'use strict';

	/** @type {import('./min')} */
	module.exports = Math.min;

	},{}],41:[function(require,module,exports){
	'use strict';

	/** @type {import('./pow')} */
	module.exports = Math.pow;

	},{}],42:[function(require,module,exports){
	'use strict';

	/** @type {import('./round')} */
	module.exports = Math.round;

	},{}],43:[function(require,module,exports){
	'use strict';

	var $isNaN = require('./isNaN');

	/** @type {import('./sign')} */
	module.exports = function sign(number) {
		if ($isNaN(number) || number === 0) {
			return number;
		}
		return number < 0 ? -1 : +1;
	};

	},{"./isNaN":38}],44:[function(require,module,exports){
	'use strict';

	var keysShim;
	if (!Object.keys) {
		// modified from https://github.com/es-shims/es5-shim
		var has = Object.prototype.hasOwnProperty;
		var toStr = Object.prototype.toString;
		var isArgs = require('./isArguments'); // eslint-disable-line global-require
		var isEnumerable = Object.prototype.propertyIsEnumerable;
		var hasDontEnumBug = !isEnumerable.call({ toString: null }, 'toString');
		var hasProtoEnumBug = isEnumerable.call(function () {}, 'prototype');
		var dontEnums = [
			'toString',
			'toLocaleString',
			'valueOf',
			'hasOwnProperty',
			'isPrototypeOf',
			'propertyIsEnumerable',
			'constructor'
		];
		var equalsConstructorPrototype = function (o) {
			var ctor = o.constructor;
			return ctor && ctor.prototype === o;
		};
		var excludedKeys = {
			$applicationCache: true,
			$console: true,
			$external: true,
			$frame: true,
			$frameElement: true,
			$frames: true,
			$innerHeight: true,
			$innerWidth: true,
			$onmozfullscreenchange: true,
			$onmozfullscreenerror: true,
			$outerHeight: true,
			$outerWidth: true,
			$pageXOffset: true,
			$pageYOffset: true,
			$parent: true,
			$scrollLeft: true,
			$scrollTop: true,
			$scrollX: true,
			$scrollY: true,
			$self: true,
			$webkitIndexedDB: true,
			$webkitStorageInfo: true,
			$window: true
		};
		var hasAutomationEqualityBug = (function () {
			/* global window */
			if (typeof window === 'undefined') { return false; }
			for (var k in window) {
				try {
					if (!excludedKeys['$' + k] && has.call(window, k) && window[k] !== null && typeof window[k] === 'object') {
						try {
							equalsConstructorPrototype(window[k]);
						} catch (e) {
							return true;
						}
					}
				} catch (e) {
					return true;
				}
			}
			return false;
		}());
		var equalsConstructorPrototypeIfNotBuggy = function (o) {
			/* global window */
			if (typeof window === 'undefined' || !hasAutomationEqualityBug) {
				return equalsConstructorPrototype(o);
			}
			try {
				return equalsConstructorPrototype(o);
			} catch (e) {
				return false;
			}
		};

		keysShim = function keys(object) {
			var isObject = object !== null && typeof object === 'object';
			var isFunction = toStr.call(object) === '[object Function]';
			var isArguments = isArgs(object);
			var isString = isObject && toStr.call(object) === '[object String]';
			var theKeys = [];

			if (!isObject && !isFunction && !isArguments) {
				throw new TypeError('Object.keys called on a non-object');
			}

			var skipProto = hasProtoEnumBug && isFunction;
			if (isString && object.length > 0 && !has.call(object, 0)) {
				for (var i = 0; i < object.length; ++i) {
					theKeys.push(String(i));
				}
			}

			if (isArguments && object.length > 0) {
				for (var j = 0; j < object.length; ++j) {
					theKeys.push(String(j));
				}
			} else {
				for (var name in object) {
					if (!(skipProto && name === 'prototype') && has.call(object, name)) {
						theKeys.push(String(name));
					}
				}
			}

			if (hasDontEnumBug) {
				var skipConstructor = equalsConstructorPrototypeIfNotBuggy(object);

				for (var k = 0; k < dontEnums.length; ++k) {
					if (!(skipConstructor && dontEnums[k] === 'constructor') && has.call(object, dontEnums[k])) {
						theKeys.push(dontEnums[k]);
					}
				}
			}
			return theKeys;
		};
	}
	module.exports = keysShim;

	},{"./isArguments":46}],45:[function(require,module,exports){
	'use strict';

	var slice = Array.prototype.slice;
	var isArgs = require('./isArguments');

	var origKeys = Object.keys;
	var keysShim = origKeys ? function keys(o) { return origKeys(o); } : require('./implementation');

	var originalKeys = Object.keys;

	keysShim.shim = function shimObjectKeys() {
		if (Object.keys) {
			var keysWorksWithArguments = (function () {
				// Safari 5.0 bug
				var args = Object.keys(arguments);
				return args && args.length === arguments.length;
			}(1, 2));
			if (!keysWorksWithArguments) {
				Object.keys = function keys(object) { // eslint-disable-line func-name-matching
					if (isArgs(object)) {
						return originalKeys(slice.call(object));
					}
					return originalKeys(object);
				};
			}
		} else {
			Object.keys = keysShim;
		}
		return Object.keys || keysShim;
	};

	module.exports = keysShim;

	},{"./implementation":44,"./isArguments":46}],46:[function(require,module,exports){
	'use strict';

	var toStr = Object.prototype.toString;

	module.exports = function isArguments(value) {
		var str = toStr.call(value);
		var isArgs = str === '[object Arguments]';
		if (!isArgs) {
			isArgs = str !== '[object Array]' &&
				value !== null &&
				typeof value === 'object' &&
				typeof value.length === 'number' &&
				value.length >= 0 &&
				toStr.call(value.callee) === '[object Function]';
		}
		return isArgs;
	};

	},{}],47:[function(require,module,exports){
	'use strict';

	var RequireObjectCoercible = require('es-object-atoms/RequireObjectCoercible');
	var callBound = require('call-bound');
	var $isEnumerable = callBound('Object.prototype.propertyIsEnumerable');
	var $push = callBound('Array.prototype.push');

	module.exports = function entries(O) {
		var obj = RequireObjectCoercible(O);
		var entrys = [];
		for (var key in obj) {
			if ($isEnumerable(obj, key)) { // checks own-ness as well
				$push(entrys, [key, obj[key]]);
			}
		}
		return entrys;
	};

	},{"call-bound":10,"es-object-atoms/RequireObjectCoercible":22}],48:[function(require,module,exports){
	'use strict';

	var define = require('define-properties');
	var callBind = require('call-bind');

	var implementation = require('./implementation');
	var getPolyfill = require('./polyfill');
	var shim = require('./shim');

	var polyfill = callBind(getPolyfill(), Object);

	define(polyfill, {
		getPolyfill: getPolyfill,
		implementation: implementation,
		shim: shim
	});

	module.exports = polyfill;

	},{"./implementation":47,"./polyfill":49,"./shim":50,"call-bind":9,"define-properties":12}],49:[function(require,module,exports){
	'use strict';

	var implementation = require('./implementation');

	module.exports = function getPolyfill() {
		return typeof Object.entries === 'function' ? Object.entries : implementation;
	};

	},{"./implementation":47}],50:[function(require,module,exports){
	'use strict';

	var getPolyfill = require('./polyfill');
	var define = require('define-properties');

	module.exports = function shimEntries() {
		var polyfill = getPolyfill();
		define(Object, { entries: polyfill }, {
			entries: function testEntries() {
				return Object.entries !== polyfill;
			}
		});
		return polyfill;
	};

	},{"./polyfill":49,"define-properties":12}],51:[function(require,module,exports){
	'use strict';

	var GetIntrinsic = require('get-intrinsic');
	var define = require('define-data-property');
	var hasDescriptors = require('has-property-descriptors')();
	var gOPD = require('gopd');

	var $TypeError = require('es-errors/type');
	var $floor = GetIntrinsic('%Math.floor%');

	/** @type {import('.')} */
	module.exports = function setFunctionLength(fn, length) {
		if (typeof fn !== 'function') {
			throw new $TypeError('`fn` is not a function');
		}
		if (typeof length !== 'number' || length < 0 || length > 0xFFFFFFFF || $floor(length) !== length) {
			throw new $TypeError('`length` must be a positive 32-bit integer');
		}

		var loose = arguments.length > 2 && !!arguments[2];

		var functionLengthIsConfigurable = true;
		var functionLengthIsWritable = true;
		if ('length' in fn && gOPD) {
			var desc = gOPD(fn, 'length');
			if (desc && !desc.configurable) {
				functionLengthIsConfigurable = false;
			}
			if (desc && !desc.writable) {
				functionLengthIsWritable = false;
			}
		}

		if (functionLengthIsConfigurable || functionLengthIsWritable || !loose) {
			if (hasDescriptors) {
				define(/** @type {Parameters<define>[0]} */ (fn), 'length', length, true, true);
			} else {
				define(/** @type {Parameters<define>[0]} */ (fn), 'length', length);
			}
		}
		return fn;
	};

	},{"define-data-property":11,"es-errors/type":20,"get-intrinsic":26,"gopd":31,"has-property-descriptors":32}],52:[function(require,module,exports){
	(function (process){(function (){
	/**
	 * Copyright (c) 2014-present, Facebook, Inc.
	 *
	 * This source code is licensed under the MIT license found in the
	 * LICENSE file in the root directory of this source tree.
	 */

	'use strict';

	/**
	 * Similar to invariant but only logs a warning if the condition is not met.
	 * This can be used to log issues in development environments in critical
	 * paths. Removing the logging code for production environments will keep the
	 * same logic and follow the same code paths.
	 */

	var __DEV__ = process.env.NODE_ENV !== 'production';

	var warning = function() {};

	if (__DEV__) {
	  var printWarning = function printWarning(format, args) {
		var len = arguments.length;
		args = new Array(len > 1 ? len - 1 : 0);
		for (var key = 1; key < len; key++) {
		  args[key - 1] = arguments[key];
		}
		var argIndex = 0;
		var message = 'Warning: ' +
		  format.replace(/%s/g, function() {
			return args[argIndex++];
		  });
		if (typeof console !== 'undefined') {
		  console.error(message);
		}
		try {
		  // --- Welcome to debugging React ---
		  // This error was thrown as a convenience so that you can use this stack
		  // to find the callsite that caused this warning to fire.
		  throw new Error(message);
		} catch (x) {}
	  }

	  warning = function(condition, format, args) {
		var len = arguments.length;
		args = new Array(len > 2 ? len - 2 : 0);
		for (var key = 2; key < len; key++) {
		  args[key - 2] = arguments[key];
		}
		if (format === undefined) {
		  throw new Error(
			  '`warning(condition, format, ...args)` requires a warning ' +
			  'message argument'
		  );
		}
		if (!condition) {
		  printWarning.apply(null, [format].concat(args));
		}
	  };
	}

	module.exports = warning;

	}).call(this)}).call(this,require('_process'))
	},{"_process":1}]},{},[2])(2)
	});
{% endraw %}
