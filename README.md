# protomerge

A CLI tool for merging [eo-protocol](https://github.com/Cirras/eo-protocol) extensions and
outputting extended protocol XML files ready to use with any eolib code generator.

---

## Installation

```bash
pip install protomerge
```

Requires Python 3.9+.

---

## Commands

| Command | Description |
|---|---|
| `protomerge apply` | Fetch extensions, merge XML, and write extended protocol files |
| `protomerge validate` | Dry-run merge to check for conflicts without writing any files |

---

## `protomerge apply`

Reads an `extensions.xml` config, fetches extension sources, merges the XML into the base
[eo-protocol](https://github.com/Cirras/eo-protocol) files, and writes the result to an
output directory.

```bash
protomerge apply --config=extensions.xml --output=./eo-protocol
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--config` | `extensions.xml` | Path to your `extensions.xml` file |
| `--output` | `./eo-protocol` | Output directory for the merged protocol XML files |

The output directory mirrors the structure of `eo-protocol/xml/` and can be passed directly
to any eolib code generator.

---

## `protomerge validate`

Fetches the base `eo-protocol` and all extensions to the local cache, then performs a
dry-run merge to check for conflicts — without writing any output files.
Useful for catching merge errors during extension development or in CI.

```bash
protomerge validate --config=extensions.xml
```

---

## `extensions.xml` format

Create an `extensions.xml` file in your project to declare which extensions to apply:

```xml
<extensions>
  <!-- Official registry extension (git, default repo) -->
  <extension type="git" name="deep"/>

  <!-- Extension from a custom repository -->
  <extension type="git"
             name="my-feature"
             repo="https://github.com/my-org/eo-protocol-extensions"/>

  <!-- Pin to a specific tag or commit -->
  <extension type="git" name="my-feature" ref="v2.0.0"
             repo="https://github.com/my-org/eo-protocol-extensions"/>

  <!-- Local file-based extension (good for development) -->
  <extension type="file" name="local-test" path="../my-extension"/>
</extensions>
```

Extensions are applied in the order they appear. Later extensions can append to or replace
definitions introduced by earlier ones.

The `path` for `type="file"` can be relative (resolved from the `extensions.xml` location)
or absolute.

---

## Extension XML format

Extension `protocol.xml` files mirror the structure of the base
[eo-protocol XML files](https://github.com/Cirras/eo-protocol).

### The `extend` attribute

`extend` can be used on top-level elements (`<enum>`, `<struct>`, `<packet>`) to control
the merge behavior:

| Value | Behavior |
|---|---|
| *(absent)* | **New** — definition must not already exist. Error if it does. |
| `"append"` | **Append** — push child elements onto an existing definition. |
| `"replace"` | **Replace** — completely swap out an existing definition. |

`extend="replace"` can also be used on individual `<value>` children inside an
`extend="append"` enum block to rename a specific existing value by its numeric position,
without replacing the whole enum:

```xml
<!-- Rename Reserved7 to Spell while leaving all other values intact -->
<enum name="ItemType" extend="append">
    <value name="Spell" extend="replace">7</value>
</enum>
```

### Appending switch cases

Use `extend="append"` on a `<switch>` child to add new `<case>` elements without replacing
the whole definition. The merger locates the target `<switch>` by its `field` attribute,
searching recursively — it works whether the switch is a direct child or nested inside a
`<chunked>` block.

```xml
<struct name="AvatarChange" extend="append">
    <switch field="change_type" extend="append">
        <case value="Skin">
            <field name="skin" type="char"/>
        </case>
    </switch>
</struct>
```

### Conflict rules

| Situation | Behavior |
|---|---|
| New definition with duplicate name | **Error** — use `extend="replace"` to override |
| Append to nonexistent target | **Error** — check name and extension order |
| Replace nonexistent target | **Error** |
| Enum append with duplicate numeric value | **Error** — numeric conflicts corrupt generated code |
| Enum value replace with nonexistent numeric value | **Error** — check the numeric value |
| Switch append with no matching `field` | **Error** — check the field name |

### Example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<protocol>
    <!-- Add a brand-new enum -->
    <enum name="Rarity" type="char">
        <value name="Common">0</value>
        <value name="Rare">1</value>
    </enum>

    <!-- Add a new value to an existing enum -->
    <enum name="PacketFamily" extend="append">
        <value name="Rarity">200</value>
    </enum>

    <!-- Rename an existing reserved value by numeric position -->
    <enum name="ItemType" extend="append">
        <value name="Spell" extend="replace">7</value>
    </enum>

    <!-- Completely replace an existing struct -->
    <struct name="Coords" extend="replace">
        <field name="x" type="short"/>
        <field name="y" type="short"/>
        <field name="layer" type="char"/>
    </struct>

    <!-- Add new cases to a switch inside an existing struct -->
    <struct name="AvatarChange" extend="append">
        <switch field="change_type" extend="append">
            <case value="Skin">
                <field name="skin" type="char"/>
            </case>
        </switch>
    </struct>

    <!-- Add a new client-to-server packet -->
    <packet family="Rarity" action="Request">
        <field name="item_id" type="short"/>
    </packet>
</protocol>
```

---

## Extension directory structure

An extension directory mirrors the layout of `eo-protocol/xml/`:

```
my-extension/
  protocol.xml              ← top-level definitions (enums, structs, misc packets)
  net/
    client/
      protocol.xml          ← client-to-server packets
    server/
      protocol.xml          ← server-to-client packets
  pub/
    protocol.xml            ← pub file type definitions (EIF, ENF, ESF, ECF)
```

Not all files are required — include only what your extension touches.

---

## License

MIT
