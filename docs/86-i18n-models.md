**[Return to documentation summary](../README.md)**

# Sharly Chess - Internationalization - Models

The translations for new locales use Huggingface models.

This page shows how models are installed and used by `i18n_check.py` (below what was done to get a working translation to French).

The model used is MarianMT:
- https://huggingface.co/docs/transformers/main/en/model_doc/marian#transformers.MarianMTModel

The English to French model was found at https://huggingface.co/Helsinki-NLP/opus-mt-en-fr?library=transformers.

Eventually the following packages were needed:
- ``transformers``
- ``torch``
- ``sentencepiece``
- ``sacremoses``

## 1. Installed packages

Installed ``transformers``.

```
MarianMTModel requires the PyTorch library but it was not found in your environment. Checkout the instructions on the installation page: https://pytorch.org/get-started/locally/ and follow the ones that match your environment.
```

Installed PyTorch from the torch package (PyTorch is provided by the torch package, not by the PyTorch which also exists).

```
ValueError: This tokenizer cannot be instantiated. Please make sure you have `sentencepiece` installed in order to use this tokenizer.
```

Installed sentencepiece

```
venv\Lib\site-packages\huggingface_hub\file_download.py:140: UserWarning: `huggingface_hub` cache-system uses symlinks by default to efficiently store duplicated files but your machine does not support them in C:\Users\paubry3\.cache\huggingface\hub\models--Helsinki-NLP--opus-mt-fr-en. Caching files will still work but in a degraded version that might require more space on your disk. This warning can be disabled by setting the `HF_HUB_DISABLE_SYMLINKS_WARNING` environment variable. For more details, see https://huggingface.co/docs/huggingface_hub/how-to-cache#limitations.
```

## 2. Removed warnings

Added the following code (cf https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables):<br/>
`HF_HUB_DISABLE_SYMLINKS_WARNING = 1`

```
venv\Lib\site-packages\transformers\models\marian\tokenization_marian.py:175: UserWarning: Recommended: pip install sacremoses.
```

Installed ``sacremoses``.

```
Can't load the model for 'Helsinki-NLP/opus-mt-fr-en'. If you were trying to load it from 'https://huggingface.co/models', make sure you don't have a local directory with the same name. Otherwise, make sure 'Helsinki-NLP/opus-mt-fr-en' is the correct path to a directory containing a file named pytorch_model.bin, tf_model.h5, model.ckpt or flax_model.msgpack.
```

## 3. Installed the model files

Got ``pytorch_model.bin`` by searching en-fr on https://huggingface.co/models: https://huggingface.co/Helsinki-NLP/opus-mt-en-fr > > Files and versions, downloaded the file and added it to folder ``Helsinki-NLP/opus-mt-en-fr``.

```
File "i18n_translate.py", line 9, in <module>
model = MarianMTModel.from_pretrained(model_name)
[...]
RuntimeError: Error(s) in loading state_dict for MarianMTModel:
size mismatch for final_logits_bias: copying a param with shape torch.Size([1, 59514]) from checkpoint, the shape in current model is torch.Size([1, 58101]).
[...]
size mismatch for model.decoder.layers.5.final_layer_norm.bias: copying a param with shape torch.Size([512]) from checkpoint, the shape in current model is torch.Size([1024]).
You may consider adding `ignore_mismatched_sizes=True` in the model `from_pretrained` method.
```

Added parameter ``ignore_mismatched_sizes``:<br>
`model = MarianMTModel.from_pretrained(model_name, ignore_mismatched_sizes=True)`

```
Some weights of MarianMTModel were not initialized from the model checkpoint at Helsinki-NLP/opus-mt-en-fr and are newly initialized: ['model.decoder.layers.10.encoder_attn.k_proj.bias', ...]
You should probably TRAIN this model on a down-stream task to be able to use it for predictions and inference.
Some weights of MarianMTModel were not initialized from the model checkpoint at Helsinki-NLP/opus-mt-en-fr and are newly initialized because the shapes did not match:
- final_logits_bias: found shape torch.Size([1, 59514]) in the checkpoint and torch.Size([1, 58101]) in the model instantiated
[...]
File "i18n_translate.py", line 10, in <module>
tokenizer = AutoTokenizer.from_pretrained(model_name)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
[...]
ValueError: Unrecognized model in Helsinki-NLP/opus-mt-en-fr. Should have a `model_type` key in its config.json, or contain one of the following strings in its name: albert, ...
```

Downloaded ``config.json`` to folder ``Helsinki-NLP/opus-mt-en-fr``.

```
File "i18n_translate.py", line 10, in <module>
tokenizer = AutoTokenizer.from_pretrained(model_name)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
[...]
OSError: Can't load tokenizer for 'Helsinki-NLP/opus-mt-en-fr'. If you were trying to load it from 'https://huggingface.co/models', make sure you don't have a local directory with the same name. Otherwise, make sure 'Helsinki-NLP/opus-mt-en-fr' is the correct path to a directory containing all relevant files for a MarianTokenizer tokenizer.
```

Downloaded ``tokenizer_config.json`` to folder ``Helsinki-NLP/opus-mt-en-fr``.

```
File "venv\Lib\site-packages\transformers\models\marian\tokenization_marian.py", line 125, in __init__
assert Path(source_spm).exists(), f"cannot find spm source {source_spm}"
       ^^^^^^^^^^^^^^^^
[...]
File "C:\Python\Python311\Lib\pathlib.py", line 493, in _parse_args
a = os.fspath(a)
    ^^^^^^^^^^^^
TypeError: expected str, bytes or os.PathLike object, not NoneType
[...]
ImportError:
requires the protobuf library but it was not found in your environment. Checkout the instructions on the installation page of its repo: https://github.com/protocolbuffers/protobuf/tree/master/python#installation and follow the ones that match your environment. Please note that you may need to restart your runtime after installation.
```

Downloaded ``source.spm`` to folder ``Helsinki-NLP/opus-mt-en-fr``:

```
File "venv\Lib\site-packages\transformers\tokenization_utils_base.py", line 2272, in _from_pretrained
File "venv\Lib\site-packages\transformers\models\marian\tokenization_marian.py", line 128, in __init__
self.encoder = load_json(vocab)
               ^^^^^^^^^^^^^^^^
[...]
TypeError: expected str, bytes or os.PathLike object, not NoneType
ImportError:
 requires the protobuf library but it was not found in your environment. Checkout the instructions on the installation page of its repo: https://github.com/protocolbuffers/protobuf/tree/master/python#installation and follow the ones that match your environment. Please note that you may need to restart your runtime after installation.
```

Downloaded ``vocab.json`` to folder ``Helsinki-NLP/opus-mt-en-fr``:

```
File "venv\Lib\site-packages\transformers\models\marian\tokenization_marian.py", line 147, in __init__
self.spm_target = load_spm(target_spm, self.sp_model_kwargs)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
[...]
TypeError: not a string
[...]
ImportError:
 requires the protobuf library but it was not found in your environment. Checkout the instructions on the
installation page of its repo: https://github.com/protocolbuffers/protobuf/tree/master/python#installation and follow the ones
that match your environment. Please note that you may need to restart your runtime after installation.
```

Downloaded ``target.spm`` to folder ``Helsinki-NLP/opus-mt-en-fr``:

Works fine ;-)
